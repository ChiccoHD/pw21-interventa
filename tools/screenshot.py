"""Screenshot della dashboard in docs/screenshot (richiede Playwright e la dashboard avviata)."""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshot"
OUT.mkdir(parents=True, exist_ok=True)


def attendi(page, grafici):
    page.wait_for_selector("[data-testid='stMetric']", timeout=60000)
    page.wait_for_function(f"document.querySelectorAll('.js-plotly-plot').length >= {grafici}", timeout=60000)
    page.wait_for_timeout(2500)


def pagina_intera(page, nome):
    altezza = page.evaluate("document.querySelector('[data-testid=\"stMain\"]').scrollHeight")
    page.set_viewport_size({"width": 1440, "height": altezza + 40})
    page.wait_for_timeout(1500)
    page.screenshot(path=OUT / nome, full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)

    page.goto(URL)
    attendi(page, 5)
    pagina_intera(page, "01_dashboard_completa.png")
    page.set_viewport_size({"width": 1440, "height": 4000})
    page.wait_for_timeout(1000)
    box = page.locator("[data-testid='stMainBlockContainer']").bounding_box()
    page.screenshot(path=OUT / "02_kpi.png",
                    clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": 430})
    for i, g in enumerate(page.locator(".js-plotly-plot").all(), start=1):
        g.screenshot(path=OUT / f"grafico_{i}.png")

    zona = page.locator("[data-testid='stSidebar'] [data-testid='stMultiSelect']").first
    for nome in ["Palermo", "Catania"]:
        zona.click()
        page.get_by_role("option", name=nome, exact=True).click()
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
    attendi(page, 5)
    pagina_intera(page, "03_filtro_palermo_catania.png")

    page.goto(URL + "/qualita")
    attendi(page, 2)
    pagina_intera(page, "04_qualita_dati.png")
    browser.close()

print(f"Screenshot salvati in {OUT}")
