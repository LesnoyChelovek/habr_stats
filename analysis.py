# -*- coding: utf-8 -*-
"""
Скрипт для анализа данных о статьях компаний Habr из JSON-файлов.

- Читает все .json файлы из директории ./company/
- Для каждой компании рассчитывает:
  - Общее количество статей
  - Среднее количество статей в месяц (2020-2025)
  - Медианное количество просмотров (2020-2025)
  - Медианное количество реакций (голоса + комменты + закладки) (2020-2025)
- Генерирует единый HTML-отчет companies_analysis.html с инфографикой.
"""

import os
import json
import glob
import statistics
import re
from datetime import datetime

# Helper functions to convert metrics from string to int
def convert_views_to_int(views_str: str) -> int:
    if not isinstance(views_str, str):
        return 0
    s = views_str.lower().strip().replace(' ', '').replace(',', '.')
    try:
        if 'k' in s:
            return int(float(s.replace('k', '')) * 1000)
        if 'm' in s:
            return int(float(s.replace('m', '')) * 1000000)
        return int(float(s))
    except (ValueError, TypeError):
        return 0

def convert_metric_to_int(metric_str: str) -> int:
    if not isinstance(metric_str, str):
        return 0
    s = metric_str.strip().replace(' ', '').replace('+', '').lower().replace(',', '.')
    try:
        if 'k' in s:
            return int(float(s.replace('k', '')) * 1000)
        if 'm' in s:
            return int(float(s.replace('m', '')) * 1000000)
        return int(float(s))
    except (ValueError, TypeError):
        return 0

def render_aggregated_html(avg_views_data: dict, avg_reactions_data: dict) -> str:
    labels = json.dumps(list(avg_views_data.keys()))
    views_data = json.dumps([float(v) if v is not None else 0 for v in avg_views_data.values()])
    reactions_data = json.dumps([float(v) if v is not None else 0 for v in avg_reactions_data.values()])
    return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Сводный анализ компаний Habr</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdn.tailwindcss.com?plugins=forms,typography"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  body {{ font-family: 'Inter', sans-serif; }}
</style>
</head>
<body class="bg-gray-50">
<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
  <header class="py-8">
    <h1 class="text-4xl font-bold mb-2">Сводный анализ по всем компаниям</h1>
    <p class="text-lg text-gray-600">Средние показатели по годам (2020-2025)</p>
  </header>
  <main class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <div class="bg-white p-6 rounded-xl shadow-md"><h3 class="font-bold mb-4 text-center">Средняя медиана просмотров</h3><div style="height: 350px;"><canvas id="avgViewsChart"></canvas></div></div>
      <div class="bg-white p-6 rounded-xl shadow-md"><h3 class="font-bold mb-4 text-center">Средняя медиана реакций</h3><div style="height: 350px;"><canvas id="avgReactionsChart"></canvas></div></div>
  </main>
</div>
<script>
  document.addEventListener('DOMContentLoaded', () => {{
    const createLineChart = (canvasId, label, data, color) => {{
        new Chart(document.getElementById(canvasId).getContext('2d'), {{
          type: 'line',
          data: {{ labels: {labels}, datasets: [{{ label, data, borderColor: color, tension: 0.1 }}] }},
          options: {{ maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});
      }};
      createLineChart('avgViewsChart', 'Средняя медиана просмотров', {views_data}, 'rgba(54, 162, 235, 1)');
      createLineChart('avgReactionsChart', 'Средняя медиана реакций', {reactions_data}, 'rgba(255, 99, 132, 1)');
  }});
</script>
</body>
</html>
"""

def render_analysis_html(companies_data: list, aggregated_data: dict) -> str:
    nav_links_html = "".join(
        f'<a href="#{d["name"]}" class="text-indigo-600 hover:underline px-3 py-2 rounded-md text-sm font-medium">{d["name"]}</a>'
        for d in companies_data
    )
    aggregated_data_json = json.dumps(aggregated_data)

    company_sections_html = ""
    chart_init_js = ""

    for data in companies_data:
        company_name_id = re.sub(r'[^a-zA-Z0-9-]','', data['name'].strip().lower().replace(' ', '-'))
        
        chart_labels = json.dumps(list(data.get('articles_per_year_20_25', {}).keys()))
        articles_data = json.dumps(list(data.get('articles_per_year_20_25', {}).values()))
        views_data = json.dumps(list(data.get('median_views_per_year_20_25', {}).values()))
        reactions_data = json.dumps(list(data.get('median_reactions_per_year_20_25', {}).values()))

        articles_canvas_id = f"articles-chart-{company_name_id}"
        views_canvas_id = f"views-chart-{company_name_id}"
        reactions_canvas_id = f"reactions-chart-{company_name_id}"

        company_sections_html += f"""
        <section id="{data['name']}" class="mb-20 scroll-mt-20">
          <h2 class="text-3xl font-bold border-b border-gray-200 pb-3 mb-6">{data['name']}</h2>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
            <div class="bg-white p-5 rounded-xl shadow-md"><p class="text-sm font-medium text-gray-500">Всего статей</p><p class="mt-1 text-3xl font-semibold">{data['total_articles']}</p></div>
            <div class="bg-white p-5 rounded-xl shadow-md"><p class="text-sm font-medium text-gray-500">Среднемес. статей (20-25)</p><p class="mt-1 text-3xl font-semibold">{data['avg_monthly_20_25']}</p></div>
            <div class="bg-white p-5 rounded-xl shadow-md"><p class="text-sm font-medium text-gray-500">Медиана просмотров (20-25)</p><p class="mt-1 text-3xl font-semibold">{int(data['median_views_20_25'])}</p></div>
            <div class="bg-white p-5 rounded-xl shadow-md"><p class="text-sm font-medium text-gray-500">Медиана реакций (20-25)</p><p class="mt-1 text-3xl font-semibold">{int(data['median_reactions_20_25'])}</p></div>
          </div>
          <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="bg-white p-6 rounded-xl shadow-md"><h3 class="font-bold mb-4 text-center">Публикации по годам</h3><div style="height: 250px;"><canvas id="{articles_canvas_id}"></canvas></div></div>
            <div class="bg-white p-6 rounded-xl shadow-md"><h3 class="font-bold mb-4 text-center">Медиана просмотров</h3><div class="flex items-center justify-end mb-2"><input id="toggle-avg-views-{company_name_id}" type="checkbox" class="h-4 w-4 rounded text-indigo-600"><label for="toggle-avg-views-{company_name_id}" class="ml-2 block text-sm">Показать среднее</label></div><div style="height: 250px;"><canvas id="{views_canvas_id}"></canvas></div></div>
            <div class="bg-white p-6 rounded-xl shadow-md"><h3 class="font-bold mb-4 text-center">Медиана реакций</h3><div class="flex items-center justify-end mb-2"><input id="toggle-avg-reactions-{company_name_id}" type="checkbox" class="h-4 w-4 rounded text-indigo-600"><label for="toggle-avg-reactions-{company_name_id}" class="ml-2 block text-sm">Показать среднее</label></div><div style="height: 250px;"><canvas id="{reactions_canvas_id}"></canvas></div></div>
          </div>
        </section>
        """

        chart_init_js += f"""
        (function() {{
          const chart_views = new Chart(document.getElementById('{views_canvas_id}').getContext('2d'), {{ type: 'line', data: {{ labels: {chart_labels}, datasets: [{{ label: 'Медиана просмотров', data: {views_data}, borderColor: 'rgba(54, 162, 235, 1)', tension: 0.1 }}, {{ label: 'Среднее по рынку', data: aggregated_data.views, borderColor: 'rgba(150, 150, 150, 0.5)', borderDash: [5, 5], tension: 0.1, hidden: true }}] }}, options: {{ maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }} }});
          const chart_reactions = new Chart(document.getElementById('{reactions_canvas_id}').getContext('2d'), {{ type: 'line', data: {{ labels: {chart_labels}, datasets: [{{ label: 'Медиана реакций', data: {reactions_data}, borderColor: 'rgba(255, 99, 132, 1)', tension: 0.1 }}, {{ label: 'Среднее по рынку', data: aggregated_data.reactions, borderColor: 'rgba(150, 150, 150, 0.5)', borderDash: [5, 5], tension: 0.1, hidden: true }}] }}, options: {{ maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }} }});
          new Chart(document.getElementById('{articles_canvas_id}').getContext('2d'), {{ type: 'bar', data: {{ labels: {chart_labels}, datasets: [{{ label: 'Кол-во статей', data: {articles_data}, backgroundColor: 'rgba(75, 192, 192, 0.6)' }}] }}, options: {{ maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ ticks: {{ precision: 0 }} }} }} }} }});
          
          document.getElementById('toggle-avg-views-{company_name_id}').addEventListener('change', (e) => {{ chart_views.setDatasetVisibility(1, e.target.checked); chart_views.update(); }});
          document.getElementById('toggle-avg-reactions-{company_name_id}').addEventListener('change', (e) => {{ chart_reactions.setDatasetVisibility(1, e.target.checked); chart_reactions.update(); }});
        }})();
        """

    html_template = f"""<!DOCTYPE html>
<html lang="ru" class="scroll-smooth">
<head>
<meta charset="UTF-8">
<title>Анализ компаний Habr</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdn.tailwindcss.com?plugins=forms,typography"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style> @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'); body {{ font-family: 'Inter', sans-serif; }} </style>
</head>
<body class="bg-gray-50">
<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
  <header class="py-8"><h1 class="text-4xl font-bold mb-2">Анализ активности компаний на Habr</h1><p class="text-lg text-gray-500">Сгенерировано: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p></header>
  <nav class="sticky top-0 z-10 bg-gray-50/80 backdrop-blur-sm py-3 mb-8 border-y border-gray-200"><div class="flex items-center flex-wrap"><span class="font-bold mr-4">Компании:</span>{nav_links_html}</div></nav>
  <main>{company_sections_html}</main>
</div>
<script>
    const aggregated_data = {aggregated_data_json};
    window.addEventListener('DOMContentLoaded', () => {{ {chart_init_js} }});
</script>
</body>
</html>"""
    return html_template

def main():
    company_dir = 'company'
    json_files = glob.glob(os.path.join(company_dir, '*.json'))

    if not json_files:
        print(f"Директория '{company_dir}' не найдена или пуста. Пожалуйста, создайте ее и поместите в нее JSON-файлы компаний.")
        return

    companies_data = []
    start_year, end_year = 2020, 2025
    num_months_period = (end_year - start_year + 1) * 12

    for file_path in json_files:
        company_name = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                articles = json.load(f)
            except json.JSONDecodeError:
                print(f"Ошибка: не удалось прочитать JSON из файла {file_path}")
                continue

        total_articles = len(articles)
        articles_20_25 = [a for a in articles if 'date' in a and a['date'] and str(start_year) <= a['date'][:4] <= str(end_year)]

        yearly_articles = {str(year): [] for year in range(start_year, end_year + 1)}
        for article in articles_20_25:
            yearly_articles[article['date'][:4]].append(article)

        articles_per_year = {year: len(arts) for year, arts in yearly_articles.items()}
        median_views_per_year = {year: statistics.median([convert_views_to_int(a.get('views', '0')) for a in arts]) if arts else 0 for year, arts in yearly_articles.items()}
        median_reactions_per_year = {year: statistics.median([(convert_metric_to_int(a.get('votes', '0')) + convert_metric_to_int(a.get('comments', '0')) + convert_metric_to_int(a.get('bookmarks', '0'))) for a in arts]) if arts else 0 for year, arts in yearly_articles.items()}

        if not articles_20_25:
            avg_monthly, overall_median_views, overall_median_reactions = 0.0, 0.0, 0.0
        else:
            avg_monthly = len(articles_20_25) / num_months_period
            overall_median_views = float(statistics.median([convert_views_to_int(a.get('views', '0')) for a in articles_20_25]))
            overall_median_reactions = float(statistics.median([(convert_metric_to_int(a.get('votes', '0')) + convert_metric_to_int(a.get('comments', '0')) + convert_metric_to_int(a.get('bookmarks', '0'))) for a in articles_20_25]))

        companies_data.append({
            'name': company_name, 'total_articles': int(total_articles), 'avg_monthly_20_25': round(float(avg_monthly), 2),
            'median_views_20_25': float(overall_median_views), 'median_reactions_20_25': float(overall_median_reactions),
            'articles_per_year_20_25': articles_per_year, 'median_views_per_year_20_25': median_views_per_year,
            'median_reactions_per_year_20_25': median_reactions_per_year,
        })

    companies_data.sort(key=lambda x: x['name'])

    years = [str(y) for y in range(start_year, end_year + 1)]
    aggregated_data = {"years": years, "views": [0.0]*len(years), "reactions": [0.0]*len(years)}
    if companies_data:
        num_companies = len(companies_data)
        avg_median_views_per_year = {year: sum(c['median_views_per_year_20_25'][year] for c in companies_data) / num_companies for year in years}
        avg_median_reactions_per_year = {year: sum(c['median_reactions_per_year_20_25'][year] for c in companies_data) / num_companies for year in years}
        
        aggregated_data = {
            "years": years,
            "views": list(avg_median_views_per_year.values()),
            "reactions": list(avg_median_reactions_per_year.values()),
        }

        agg_html_content = render_aggregated_html(avg_median_views_per_year, avg_median_reactions_per_year)
        with open('aggregated_analysis.html', 'w', encoding='utf-8') as f:
            f.write(agg_html_content)
        print("Сводный анализ сохранен в файле: aggregated_analysis.html")

    html_content = render_analysis_html(companies_data, aggregated_data)
    output_filename = 'companies_analysis.html'
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Детальный анализ сохранен в файле: {output_filename}")

if __name__ == "__main__":
    main()