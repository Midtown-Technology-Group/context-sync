# Context Sync - Project Site

A simple, single-page project site for Context Sync. Designed for GitHub Pages.

## Deploy to GitHub Pages

### Option 1: Root Domain (midtown-technology-group.github.io/context-sync/)

1. In your GitHub repo, go to **Settings → Pages**
2. Under "Build and deployment" select **Deploy from a branch**
3. Select `gh-pages` branch and `/ (root)` folder
4. Click Save

Then push this folder to the gh-pages branch:

```bash
git checkout --orphan gh-pages
git rm -rf .
cp -r ../work-context-sync-site/* .
git add .
git commit -m "Initial site"
git push origin gh-pages
```

### Option 2: `/docs` folder on main branch

1. Move these files to a `docs/` folder in your main branch
2. In GitHub repo: **Settings → Pages**
3. Select **Deploy from a branch** → `main` → `/docs`

### Option 3: Custom Domain (context-sync.midtowntg.com)

1. Add a file named `CNAME` containing your domain:
   ```
   context-sync.midtowntg.com
   ```
2. Push to gh-pages branch
3. In your DNS, add a CNAME record:
   - Name: `context-sync`
   - Value: `midtown-technology-group.github.io`
4. In GitHub repo: **Settings → Pages**, enter your custom domain

## Local Preview

Simply open `index.html` in a browser, or use a local server:

```bash
python -m http.server 8000
# or
npx serve .
```

## Customization

- Edit colors in `styles.css` (CSS variables at the top)
- Replace logo SVG in `index.html` with your own
- Update feature descriptions, installation steps, etc.

## License

Site content under same AGPL-3.0 license as the project.
