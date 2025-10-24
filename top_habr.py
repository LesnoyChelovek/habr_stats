# -*- coding: utf-8 -*-
"""
Асинхронный парсер 5 лучших по просмотрам статей за каждый год с Habr.

Что умеет:
- Грузит все страницы из https://habr.com/ru/articles/top/alltime/
- Для каждого года находит 5 статей с наибольшим количеством просмотров.
- Конвертирует просмотры (e.g., '25.6k', '1.2M') в числа для корректной сортировки.
- Сохраняет результат в один JSON-файл.

Примеры запуска:
    python top_habr.py
    python top_habr.py -o top.json --timeout 15
"""

import asyncio
import aiohttp
import json
import statistics
from bs4 import BeautifulSoup
from datetime import datetime
import os
import argparse

# Базовая часть домена Habr для сборки абсолютных ссылок на статьи
BASE_URL = "https://habr.com"

# Значения по умолчанию (могут быть переопределены через аргументы)
REQUEST_TIMEOUT_DEFAULT = 12
USER_AGENT = "Mozilla/5.0 (compatible; TopHabrScraper/1.0; +https://habr.com)"
OUTPUT_FILENAME_DEFAULT = "top_article.json"


def format_number(text: str) -> str:
    """
    Аккуратное форматирование числовых значений (просмотры/закладки/оценки),
    замена неразрывных пробелов и тримминг.
    """
    if not text:
        return "N/A"
    s = text.strip().replace("\xa0", " ")
    return s


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str | None:
    """
    Асинхронно получает HTML по указанному URL.
    Возвращает строку HTML или None при ошибке/таймауте.
    """
    try:
        async with session.get(url, timeout=session.timeout) as resp:
            resp.raise_for_status()
            return await resp.text()
    except Exception as e:
        print(f"Fetch error {url}: {e}")
        return None


def parse_pagination_last_page(html: str) -> int:
    """
    Находит блок пагинации и извлекает номер последней страницы.
    Если пагинации нет или парсинг не удался — возвращает 1.
    """
    soup = BeautifulSoup(html, "html.parser")
    pagination_block = soup.find("div", class_="tm-pagination", attrs={"data-test-id": "pagination"})
    if not pagination_block:
        return 1
    page_links = pagination_block.find_all("a", class_="tm-pagination__page")
    if not page_links:
        return 1
    try:
        return int(page_links[-1].text.strip())
    except Exception:
        return 1


def parse_article_block(article_block) -> dict:
    """
    Парсит один блок статьи из списка:
    - заголовок и URL
    - автор
    - дата/время публикации
    - метрики: просмотры, оценки, комментарии, закладки
    Возвращает словарь с данными по статье.
    """
    # Заголовок + URL
    title_element = article_block.find("h2", class_="tm-title tm-title_h2", attrs={"data-test-id": "articleTitle"})
    link_element = article_block.find(
        "a",
        class_="tm-title__link",
        attrs={"data-article-link": "true", "data-test-id": "article-snippet-title-link"},
    )
    title = title_element.find("span").text.strip() if title_element and title_element.find("span") else "N/A"
    url = BASE_URL + link_element["href"] if link_element and link_element.get("href") else "N/A"

    # Автор
    author_element = article_block.find("span", class_="tm-user-info__user", attrs={"data-test-id": "user-info-description"})
    author_name = "N/A"
    if author_element:
        a_user = author_element.find("a", class_="tm-user-info__username")
        if a_user:
            author_name = a_user.text.strip()

    # Дата/время (атрибут datetime у <time> обычно ISO8601)
    time_element = article_block.find("time")
    date_str = "N/A"
    time_str = "N/A"
    if time_element and time_element.get("datetime"):
        iso = time_element.get("datetime").strip()
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M")
        except Exception:
            date_str = iso[:10]
            try:
                time_str = iso.split("T")[1][:5]
            except Exception:
                time_str = "N/A"

    # Просмотры
    views_parent_span = article_block.find("span", class_="tm-icon-counter tm-data-icons__item")
    views_value = "N/A"
    if views_parent_span:
        vv = views_parent_span.find("span", class_="tm-icon-counter__value")
        if vv:
            views_value = format_number(vv.get("title") or vv.text)

    # Оценка (голоса)
    votes_element = article_block.find("div", class_="tm-votes-meter tm-data-icons__item")
    votes_value = "N/A"
    if votes_element:
        vm = votes_element.find("span", class_="tm-votes-meter__value", attrs={"data-test-id": "votes-meter-value"})
        if vm and vm.text:
            votes_value = vm.text.strip()

    # Комментарии
    comments_value = "N/A"
    comments_wrapper = article_block.find(
        "div",
        class_="article-comments-counter-link-wrapper tm-data-icons__item"
    )
    if comments_wrapper:
        span_val = comments_wrapper.find("span", class_="value")
        if span_val and span_val.text:
            comments_value = span_val.text.strip()

    # Закладки (избранное)
    bookmarks_value = "N/A"
    bookmarks_button = article_block.find("button", class_="bookmarks-button tm-data-icons__item")
    if bookmarks_button:
        counter_span = bookmarks_button.find("span", class_="bookmarks-button__counter")
        if counter_span:
            text_val = counter_span.text.strip() if counter_span.text else ""
            title_val = (counter_span.get("title") or "").strip()
            bookmarks_value = format_number(text_val or title_val)

    return {
        "url": url,
        "title": title,
        "author": author_name,
        "date": date_str,
        "time": time_str,
        "votes": votes_value,
        "comments": comments_value,
        "bookmarks": bookmarks_value,
        "views": views_value,
    }


def parse_articles_list(html: str) -> list[dict]:
    """
    Парсит список статей на странице.
    """
    soup = BeautifulSoup(html, "html.parser")
    article_blocks = soup.find_all("article", class_="tm-articles-list__item")
    results = []
    for block in article_blocks:
        try:
            results.append(parse_article_block(block))
        except Exception as e:
            print(f"Parse article error: {e}")
    return results


def convert_views_to_int(views_str: str) -> int:
    """
    Конвертирует строку просмотров (e.g., '25.6k', '1.2M', '500') в число.
    """
    if not isinstance(views_str, str):
        return 0
    views_str = views_str.lower().strip().replace(' ', '').replace(',', '.')
    if 'k' in views_str:
        try:
            return int(float(views_str.replace('k', '')) * 1000)
        except ValueError:
            return 0
    if 'm' in views_str:
        try:
            return int(float(views_str.replace('m', '')) * 1000000)
        except ValueError:
            return 0
    try:
        return int(views_str)
    except (ValueError, TypeError):
        return 0


def render_chart_html(median_data: dict, top_article_data: dict) -> str:
    """
    Генерирует HTML-страницу с графиком медианного и максимального количества просмотров по годам.
    """
    # Sort data by year for the chart
    sorted_years = sorted(median_data.keys())
    labels = json.dumps(sorted_years)
    
    median_data_points = json.dumps([median_data.get(year, 0) for year in sorted_years])
    top_data_points = json.dumps([top_article_data.get(year, 0) for year in sorted_years])

    html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Анализ просмотров статей на Habr по годам</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f2f5; }}
        .chart-container {{ width: 80%; max-width: 900px; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    </style>
</head>
<body>
    <div class="chart-container">
        <canvas id="viewsChart"></canvas>
    </div>
    <script>
        const ctx = document.getElementById('viewsChart').getContext('2d');
        const viewsChart = new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {labels},
                datasets: [
                {{
                    label: 'Медианное количество просмотров',
                    data: {median_data_points},
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    borderWidth: 2,
                    tension: 0.1
                }},
                {{
                    label: 'Просмотры топ-1 статьи',
                    data: {top_data_points},
                    borderColor: 'rgba(255, 99, 132, 1)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    borderWidth: 2,
                    tension: 0.1
                }}
              ]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Анализ просмотров статей на Habr по годам',
                        font: {{ size: 18 }}
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{
                            display: true,
                            text: 'Просмотры'
                        }}
                    }},
                    x: {{
                        title: {{
                            display: true,
                            text: 'Год'
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
    """
    return html

async def scrape_articles(base_url: str, request_timeout: int) -> list[dict]:
    """
    Загружает все страницы из раздела и парсит все статьи.
    Добавлена задержка для избежания блокировки.
    """
    headers = {"User-Agent": USER_AGENT}
    timeout = aiohttp.ClientTimeout(total=request_timeout)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        print(f"Загрузка первой страницы: {base_url}")
        first_page_html = await fetch_html(session, base_url)
        if not first_page_html:
            return []

        last_page = parse_pagination_last_page(first_page_html)
        print(f"Всего страниц для парсинга: {last_page}")
        rows = parse_articles_list(first_page_html)

        if last_page > 1:
            page_numbers = range(2, last_page + 1)
            chunk_size = 10

            for i in range(0, len(page_numbers), chunk_size):
                chunk = page_numbers[i:i + chunk_size]
                tasks = []
                for page_num in chunk:
                    url = f"{base_url}page{page_num}/"
                    tasks.append(fetch_html(session, url))

                if tasks:
                    print(f"Загрузка страниц с {chunk[0]} по {chunk[-1]}...")
                    pages_html = await asyncio.gather(*tasks)
                    for html in pages_html:
                        if html:
                            rows.extend(parse_articles_list(html))
                        # Небольшая пауза между парсингом страниц для снижения нагрузки
                        await asyncio.sleep(0.01)

                # Если это не последняя пачка, делаем паузу
                if i + chunk_size < len(page_numbers):
                    print(f"Обработана пачка из {len(chunk)} страниц. Пауза 30 секунд...")
                    await asyncio.sleep(30)

        return rows


def parse_args() -> argparse.Namespace:
    """
    Определяет и парсит аргументы командной строки.
    """
    parser = argparse.ArgumentParser(
        description="Парсер 5 лучших статей за каждый год с Habr."
    )
    parser.add_argument(
        "-o", "--output",
        default=OUTPUT_FILENAME_DEFAULT,
        help=f"Имя выходного JSON-файла (по умолчанию {OUTPUT_FILENAME_DEFAULT})"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=REQUEST_TIMEOUT_DEFAULT,
        help=f"Таймаут HTTP-запросов в секундах (по умолчанию {REQUEST_TIMEOUT_DEFAULT})"
    )
    return parser.parse_args()


async def main_async() -> None:
    """
    Асинхронная точка входа:
    - парсит аргументы
    - парсит все статьи с https://habr.com/ru/articles/top/alltime/
    - группирует по годам, находит 5 лучших и считает медиану просмотров
    - сохраняет результат в JSON и HTML-отчет с графиком
    """
    args = parse_args()
    
    base_url = "https://habr.com/ru/articles/top/alltime/"
    
    all_articles = await scrape_articles(base_url, args.timeout)

    if not all_articles:
        print("Не удалось загрузить статьи.")
        return

    # Добавляем числовое значение просмотров для сортировки
    for article in all_articles:
        article['views_int'] = convert_views_to_int(article['views'])

    # Группируем статьи по годам в диапазоне 2011-2025
    articles_by_year = {}
    for article in all_articles:
        try:
            year = int(article['date'][:4])
            if 2011 <= year <= 2025:
                if year not in articles_by_year:
                    articles_by_year[year] = []
                articles_by_year[year].append(article)
        except (ValueError, KeyError, TypeError, IndexError):
            print(f"Некорректная дата для статьи: {article.get('title')}")
            continue

    # Рассчитываем медианное количество просмотров для каждого года
    median_views_by_year = {}
    for year, articles in articles_by_year.items():
        if articles:
            all_views = [a.get('views_int', 0) for a in articles]
            median_views_by_year[year] = statistics.median(all_views)

    # Для каждого года выбираем 5 лучших для JSON-файла
    top_articles_by_year = {}
    for year, articles in sorted(articles_by_year.items(), key=lambda item: item[0], reverse=True):
        sorted_articles = sorted(articles, key=lambda x: x.get('views_int', 0), reverse=True)
        top_articles_by_year[year] = sorted_articles[:5]

    # Получаем просмотры топ-1 статьи для каждого года для графика
    top_article_views_by_year = {}
    for year, articles in top_articles_by_year.items():
        if articles:
            top_article_views_by_year[year] = articles[0].get('views_int', 0)

    # Генерируем и сохраняем HTML с графиком
    if median_views_by_year:
        chart_html = render_chart_html(median_views_by_year, top_article_views_by_year)
        chart_filename = "top_articles_analysis.html"
        chart_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), chart_filename)
        with open(chart_path, "w", encoding="utf-8") as f:
            f.write(chart_html)
        print(f"HTML-отчет с анализом сохранен в: {chart_path}")

    # Сохраняем результат в JSON
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.output)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(top_articles_by_year, f, ensure_ascii=False, indent=4)
    
    print(f"Топ статей сохранен в: {out_path}")


def main() -> None:
    """
    Синхронная точка входа, запускает асинхронную часть.
    """
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
