"""Meeting analytics - analyze calendar patterns and focus time."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, time
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from ..graph_client import GraphClient

logger = logging.getLogger("work_context_sync.analytics.meetings")


@dataclass
class MeetingMetrics:
    """Metrics for a single meeting."""
    subject: str
    start: datetime
    end: datetime
    duration_minutes: int
    organizer: str
    attendee_count: int
    is_recurring: bool
    is_online: bool
    categories: List[str]
    
    @property
    def is_focus_time(self) -> bool:
        """Check if this is a focus time block (self-scheduled, no attendees)."""
        return self.attendee_count <= 1 and not self.is_online


@dataclass
class DailyAnalytics:
    """Analytics for a single day."""
    date: date
    
    # Time breakdown
    total_meeting_minutes: int = 0
    total_focus_minutes: int = 0
    total_free_minutes: int = 0
    
    # Meeting counts
    meeting_count: int = 0
    recurring_count: int = 0
    online_count: int = 0
    
    # Quality metrics
    back_to_back_count: int = 0  # Meetings <15 min apart
    fragmentation_score: float = 0.0  # 0-100, lower is better
    longest_focus_block_minutes: int = 0
    focus_blocks: List[Tuple[datetime, datetime]] = field(default_factory=list)
    
    # Patterns
    busiest_hour: Optional[int] = None
    organizer_frequency: Dict[str, int] = field(default_factory=dict)


@dataclass
class WeeklyReport:
    """Weekly meeting analytics report."""
    start_date: date
    end_date: date
    daily_reports: List[DailyAnalytics] = field(default_factory=list)
    
    # Aggregates
    total_meeting_hours: float = 0.0
    avg_daily_meeting_hours: float = 0.0
    total_focus_hours: float = 0.0
    fragmentation_trend: List[float] = field(default_factory=list)
    
    # Insights
    insights: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class MeetingAnalyzer:
    """Analyze calendar patterns for focus time and meeting health."""
    
    def __init__(self, graph_client: GraphClient, timezone: str = "America/Indiana/Indianapolis"):
        self.client = graph_client
        self.timezone = timezone
    
    def analyze_day(self, target_date: date) -> DailyAnalytics:
        """Analyze a single day's calendar."""
        from zoneinfo import ZoneInfo
        
        tz = ZoneInfo(self.timezone)
        day_start = datetime.combine(target_date, time.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        
        # Fetch calendar
        params = {
            "startDateTime": day_start.isoformat(),
            "endDateTime": day_end.isoformat(),
            "$select": "subject,start,end,organizer,attendees,isOnlineMeeting,categories,recurrence",
            "$orderby": "start/dateTime"
        }
        
        try:
            response = self.client.get_all("/me/calendarView", params=params)
            events = response.get("value", [])
            
            return self._calculate_daily_metrics(target_date, events)
            
        except Exception as e:
            logger.error(f"Failed to analyze day {target_date}: {e}")
            return DailyAnalytics(date=target_date)
    
    def analyze_week(self, start_date: date) -> WeeklyReport:
        """Analyze a full week (7 days)."""
        end_date = start_date + timedelta(days=6)
        
        report = WeeklyReport(start_date=start_date, end_date=end_date)
        
        for i in range(7):
            day = start_date + timedelta(days=i)
            daily = self.analyze_day(day)
            report.daily_reports.append(daily)
            
            report.total_meeting_hours += daily.total_meeting_minutes / 60
            report.total_focus_hours += daily.total_focus_minutes / 60
            report.fragmentation_trend.append(daily.fragmentation_score)
        
        report.avg_daily_meeting_hours = report.total_meeting_hours / 7
        
        # Generate insights
        report.insights = self._generate_insights(report)
        report.recommendations = self._generate_recommendations(report)
        
        return report
    
    def _calculate_daily_metrics(self, target_date: date, events: List[Dict]) -> DailyAnalytics:
        """Calculate metrics from raw events."""
        analytics = DailyAnalytics(date=target_date)
        
        meetings = []
        for event in events:
            # Skip timeblocks (we created those)
            if "TimeBlock" in event.get("categories", []):
                continue
            
            # Skip all-day events
            if event.get("isAllDay"):
                continue
            
            try:
                start = datetime.fromisoformat(event["start"]["dateTime"])
                end = datetime.fromisoformat(event["end"]["dateTime"])
                duration = (end - start).total_seconds() / 60
                
                # Skip if no duration
                if duration <= 0:
                    continue
                
                # Count attendees
                attendees = event.get("attendees", [])
                attendee_count = len(attendees) + 1  # +1 for organizer
                
                # Extract organizer
                organizer = event.get("organizer", {}).get("emailAddress", {}).get("name", "Unknown")
                
                meeting = MeetingMetrics(
                    subject=event.get("subject", "(no subject)"),
                    start=start,
                    end=end,
                    duration_minutes=int(duration),
                    organizer=organizer,
                    attendee_count=attendee_count,
                    is_recurring=event.get("recurrence") is not None,
                    is_online=event.get("isOnlineMeeting", False),
                    categories=event.get("categories", [])
                )
                
                meetings.append(meeting)
                
                # Update counts
                analytics.meeting_count += 1
                analytics.total_meeting_minutes += int(duration)
                
                if meeting.is_recurring:
                    analytics.recurring_count += 1
                if meeting.is_online:
                    analytics.online_count += 1
                
                # Track organizer frequency
                analytics.organizer_frequency[organizer] = analytics.organizer_frequency.get(organizer, 0) + 1
                
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed event: {e}")
                continue
        
        # Calculate focus time (gaps between meetings)
        analytics.focus_blocks = self._find_focus_blocks(meetings, target_date)
        analytics.total_focus_minutes = sum(
            (end - start).total_seconds() / 60 
            for start, end in analytics.focus_blocks
        )
        analytics.longest_focus_block_minutes = max(
            [(end - start).total_seconds() / 60 for start, end in analytics.focus_blocks] or [0]
        )
        
        # Calculate fragmentation
        analytics.fragmentation_score = self._calculate_fragmentation(meetings)
        
        # Find busiest hour
        if meetings:
            hour_counts = defaultdict(int)
            for m in meetings:
                hour_counts[m.start.hour] += 1
            analytics.busiest_hour = max(hour_counts, key=hour_counts.get)
        
        # Count back-to-back meetings
        sorted_meetings = sorted(meetings, key=lambda m: m.start)
        for i in range(len(sorted_meetings) - 1):
            gap = (sorted_meetings[i + 1].start - sorted_meetings[i].end).total_seconds() / 60
            if gap < 15:  # Less than 15 min gap
                analytics.back_to_back_count += 1
        
        return analytics
    
    def _find_focus_blocks(
        self, 
        meetings: List[MeetingMetrics], 
        target_date: date,
        min_block_minutes: int = 90
    ) -> List[Tuple[datetime, datetime]]:
        """Find 90+ minute gaps between meetings (focus time)."""
        from zoneinfo import ZoneInfo
        
        if not meetings:
            # Entire workday is free
            tz = ZoneInfo(self.timezone)
            start = datetime.combine(target_date, time(8, 0), tzinfo=tz)
            end = datetime.combine(target_date, time(17, 30), tzinfo=tz)
            return [(start, end)]
        
        # Sort by start time
        sorted_meetings = sorted(meetings, key=lambda m: m.start)
        
        focus_blocks = []
        work_day_start = datetime.combine(
            target_date, 
            time(8, 0), 
            tzinfo=sorted_meetings[0].start.tzinfo
        )
        work_day_end = datetime.combine(
            target_date, 
            time(17, 30), 
            tzinfo=sorted_meetings[0].start.tzinfo
        )
        
        # Check gap before first meeting
        first_meeting = sorted_meetings[0]
        if (first_meeting.start - work_day_start).total_seconds() / 60 >= min_block_minutes:
            focus_blocks.append((work_day_start, first_meeting.start))
        
        # Check gaps between meetings
        for i in range(len(sorted_meetings) - 1):
            gap_start = sorted_meetings[i].end
            gap_end = sorted_meetings[i + 1].start
            gap_minutes = (gap_end - gap_start).total_seconds() / 60
            
            if gap_minutes >= min_block_minutes:
                focus_blocks.append((gap_start, gap_end))
        
        # Check gap after last meeting
        last_meeting = sorted_meetings[-1]
        if (work_day_end - last_meeting.end).total_seconds() / 60 >= min_block_minutes:
            focus_blocks.append((last_meeting.end, work_day_end))
        
        return focus_blocks
    
    def _calculate_fragmentation(self, meetings: List[MeetingMetrics]) -> float:
        """
        Calculate fragmentation score (0-100).
        
        Higher = more fragmented (worse for productivity).
        Based on:
        - Number of meetings
        - Average gap between meetings
        - Back-to-back ratio
        """
        if len(meetings) < 2:
            return 0.0  # Not fragmented if few meetings
        
        sorted_meetings = sorted(meetings, key=lambda m: m.start)
        
        # Calculate average gap
        gaps = []
        for i in range(len(sorted_meetings) - 1):
            gap = (sorted_meetings[i + 1].start - sorted_meetings[i].end).total_seconds() / 60
            gaps.append(gap)
        
        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        
        # Fragmentation factors
        meeting_count_factor = min(len(meetings) * 5, 40)  # Cap at 40
        gap_factor = max(0, (60 - avg_gap) / 60 * 30)  # Lower gap = higher fragmentation
        
        # Back-to-back penalty
        back_to_back = sum(1 for g in gaps if g < 15)
        back_to_back_factor = back_to_back * 10
        
        return min(meeting_count_factor + gap_factor + back_to_back_factor, 100)
    
    def _generate_insights(self, report: WeeklyReport) -> List[str]:
        """Generate insights from weekly data."""
        insights = []
        
        # Overall meeting load
        if report.total_meeting_hours > 30:
            insights.append(f"📊 Heavy meeting week: {report.total_meeting_hours:.1f} hours in meetings")
        elif report.total_meeting_hours < 10:
            insights.append(f"📊 Light meeting week: {report.total_meeting_hours:.1f} hours in meetings")
        
        # Focus time
        avg_focus = report.total_focus_hours / 7
        if avg_focus < 2:
            insights.append(f"⚠️ Low focus time: only {avg_focus:.1f} hours/day on average")
        elif avg_focus > 4:
            insights.append(f"✅ Excellent focus time: {avg_focus:.1f} hours/day on average")
        
        # Fragmentation trend
        if len(report.fragmentation_trend) >= 2:
            first_half = sum(report.fragmentation_trend[:3]) / 3
            second_half = sum(report.fragmentation_trend[4:]) / 3
            
            if second_half > first_half + 10:
                insights.append("📈 Fragmentation increasing over the week")
            elif second_half < first_half - 10:
                insights.append("📉 Fragmentation decreasing over the week (good!)")
        
        # Busiest day
        if report.daily_reports:
            busiest = max(report.daily_reports, key=lambda d: d.total_meeting_minutes)
            if busiest.total_meeting_minutes > 360:  # 6+ hours
                insights.append(f"🔥 Busiest day: {busiest.date.strftime('%A')} with {busiest.total_meeting_minutes / 60:.1f} hours of meetings")
        
        # Recurring meetings
        total_recurring = sum(d.recurring_count for d in report.daily_reports)
        if total_recurring > 15:
            insights.append(f"🔄 {total_recurring} recurring meetings this week ({total_recurring / 7:.1f}/day)")
        
        return insights
    
    def _generate_recommendations(self, report: WeeklyReport) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # Focus time recommendations
        days_with_low_focus = [
            d for d in report.daily_reports 
            if d.total_focus_minutes < 120  # <2 hours
        ]
        
        if days_with_low_focus:
            day_names = ", ".join([d.date.strftime("%A") for d in days_with_low_focus[:3]])
            recommendations.append(f"💡 Block 2+ hour focus sessions on {day_names}")
        
        # Back-to-back meetings
        total_back_to_back = sum(d.back_to_back_count for d in report.daily_reports)
        if total_back_to_back > 5:
            recommendations.append(f"💡 Add 15-min buffers between meetings ({total_back_to_back} back-to-backs detected)")
        
        # Fragmentation
        high_fragmentation_days = [
            d for d in report.daily_reports 
            if d.fragmentation_score > 60
        ]
        
        if high_fragmentation_days:
            recommendations.append(
                f"💡 Consider 'meeting-free mornings' on {[d.date.strftime('%A') for d in high_fragmentation_days[0:2]]}"
            )
        
        # Longest focus block suggestions
        for day in report.daily_reports:
            if day.longest_focus_block_minutes >= 120:  # 2+ hours
                recommendations.append(
                    f"💡 Protect your {day.longest_focus_block_minutes / 60:.1f}h focus block on {day.date.strftime('%A')} at {day.focus_blocks[0][0].strftime('%H:%M')}"
                )
                break  # Just suggest the first one
        
        return recommendations
    
    def to_markdown(self, report: WeeklyReport) -> str:
        """Convert weekly report to markdown for daily note."""
        lines = [
            "## 📊 Meeting Analytics Report",
            f"**Week:** {report.start_date} to {report.end_date}",
            "",
            "### Summary",
            f"- **Total meeting time:** {report.total_meeting_hours:.1f} hours ({report.avg_daily_meeting_hours:.1f}/day avg)",
            f"- **Total focus time:** {report.total_focus_hours:.1f} hours ({report.total_focus_hours / 7:.1f}/day avg)",
            f"- **Fragmentation trend:** {self._trend_emoji(report.fragmentation_trend)}",
            "",
            "### Daily Breakdown",
            "| Day | Meetings | Focus Time | Fragmentation |",
            "|-----|----------|------------|---------------|",
        ]
        
        for day in report.daily_reports:
            emoji = "🟢" if day.fragmentation_score < 40 else "🟡" if day.fragmentation_score < 70 else "🔴"
            lines.append(
                f"| {day.date.strftime('%a')} | "
                f"{day.meeting_count} ({day.total_meeting_minutes / 60:.1f}h) | "
                f"{day.total_focus_minutes / 60:.1f}h | "
                f"{emoji} {day.fragmentation_score:.0f} |"
            )
        
        if report.insights:
            lines.extend(["", "### Insights"])
            for insight in report.insights:
                lines.append(f"- {insight}")
        
        if report.recommendations:
            lines.extend(["", "### Recommendations"])
            for rec in report.recommendations:
                lines.append(f"- {rec}")
        
        lines.append("")
        return "\n".join(lines)
    
    def _trend_emoji(self, trend: List[float]) -> str:
        """Get emoji for fragmentation trend."""
        if len(trend) < 2:
            return "➡️ Stable"
        
        first = sum(trend[:3]) / 3 if len(trend) >= 3 else trend[0]
        last = sum(trend[-3:]) / 3 if len(trend) >= 3 else trend[-1]
        
        if last < first - 5:
            return "📉 Improving"
        elif last > first + 5:
            return "📈 Increasing"
        else:
            return "➡️ Stable"
