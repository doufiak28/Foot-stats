name: Foot-stats - Actualisation des cotes

"on":
  push:
    branches: [main]
  workflow_dispatch:
  schedule:
    - cron: '17 8 * * *'
    - cron: '43 15 * * 6,0'

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: footstats-odds-pages
  cancel-in-progress: false

jobs:
  publish:
    runs-on: ubuntu-latest
    timeout-minutes: 12
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Telecharger les cotes 1X2
        env:
          ODDS_API_KEY: ${{ secrets.ODDS_API_KEY }}
        run: python scripts/update_odds.py
      - name: Enregistrer les cotes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/live_odds.json
          if ! git diff --cached --quiet; then
            git commit -m "Actualisation des cotes 1X2"
            git push
          fi
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - id: deployment
        uses: actions/deploy-pages@v4
