#!/usr/bin/env python3
"""
Library Book Checkout Scraper
Scrapes checked-out books from Japanese public library OPAC systems
and generates a simple HTML table page.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Book:
    title: str
    author: str = ""
    publisher: str = ""
    year: str = ""
    checkout_date: str = ""
    due_date: str = ""
    is_overdue: bool = False
    library_name: str = ""


def parse_book_item(item, library_name: str) -> Optional[Book]:
    """Parse a single li book item from the OPAC lending list."""
    book = Book(title="", library_name=library_name)

    delay_span = item.find("span", class_="icon-delay")
    if delay_span:
        book.is_overdue = True

    title_span = item.find("span", class_="title")
    if title_span:
        title_text = title_span.get_text(separator=" ", strip=True)
        book.title = re.sub(r'\s+', ' ', title_text).strip()

    info_div = item.find("div", class_="column info")
    if info_div:
        paragraphs = info_div.find_all("p")
        if len(paragraphs) >= 1:
            info_text = paragraphs[0].get_text(strip=True)
            parts = [p.strip() for p in info_text.split("--")]
            if len(parts) >= 1 and parts[0]:
                book.author = parts[0]
            if len(parts) >= 2 and parts[1]:
                book.publisher = parts[1]
            if len(parts) >= 3 and parts[2]:
                book.year = parts[2]

        if len(paragraphs) >= 2:
            date_text = paragraphs[1].get_text(strip=True)
            checkout_match = re.search(r'貸出日[：:]?\s*([\d./]+)', date_text)
            due_match = re.search(r'返却予定日[：:]?\s*([\d./]+)', date_text)
            if checkout_match:
                book.checkout_date = checkout_match.group(1)
            if due_match:
                book.due_date = due_match.group(1)

    if book.title:
        return book
    return None


def scrape_winj_library(base_url: str, library_name: str, card_number: str, password: str) -> List[Book]:
    """Scrape checked-out books from a winj/opac-based library OPAC."""
    session = requests.Session()
    books = []

    login_page_url = base_url + "/winj/opac/login.do?lang=ja&dispatch=/opac/mylibrary.do"
    session.get(login_page_url, timeout=15)

    login_data = {
        "txt_usercd": card_number,
        "txt_password": password,
        "submit_btn_login": "ログイン",
    }
    resp = session.post(
        base_url + "/winj/opac/login.do",
        data=login_data,
        timeout=15,
        headers={
            "Referer": login_page_url,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base_url,
        },
    )

    if "誤り" in resp.text:
        print("ERROR: Login failed - incorrect card number or password")
        return []

    lend_url = base_url + "/winj/opac/lend-list.do"
    resp = session.get(lend_url, timeout=15, headers={"Referer": resp.url})
    soup = BeautifulSoup(resp.text, "html.parser")

    form = soup.find("form", attrs={"name": "PageForm"})
    if form:
        hidden_session = form.find("input", attrs={"name": "hid_session"})
        session_val = hidden_session.get("value", "") if hidden_session else ""
        reload_data = {
            "hid_session": session_val,
            "idx": "",
            "opt_pagesize": "50",
            "submit_btn_reload": "再表示",
        }
        resp = session.post(lend_url, data=reload_data, timeout=15,
                            headers={"Referer": lend_url})
        soup = BeautifulSoup(resp.text, "html.parser")

    book_list = soup.find("ol", class_="list-book")
    if not book_list:
        print("WARNING: Could not find book list on page")
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        return []

    items = book_list.find_all("li", recursive=False)
    for item in items:
        book = parse_book_item(item, library_name)
        if book:
            books.append(book)

    nav = soup.find("div", class_="nav-area")
    if nav:
        total_match = re.search(r'全(\d+)\s*件', nav.get_text())
        if total_match:
            total = int(total_match.group(1))
            print("  Total books reported: " + str(total) + ", parsed so far: " + str(len(books)))
            page = 2
            while len(books) < total:
                page_url = lend_url + "?page=" + str(page)
                resp = session.get(page_url, timeout=15, headers={"Referer": lend_url})
                page_soup = BeautifulSoup(resp.text, "html.parser")
                page_list = page_soup.find("ol", class_="list-book")
                if not page_list:
                    break
                page_items = page_list.find_all("li", recursive=False)
                if not page_items:
                    break
                for item in page_items:
                    book = parse_book_item(item, library_name)
                    if book:
                        books.append(book)
                page += 1

    return books


def scrape_tama_library(card_number: str, password: str) -> List[Book]:
    """Scrape checked-out books from Tama City Library OPAC."""
    base_url = "https://www.library.tama.tokyo.jp"
    library_name = "多摩市立図書館"
    session = requests.Session()
    books = []

    # Step 1: GET login page to get form action with jsessionid
    login_url = base_url + "/login"
    resp = session.get(login_url, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the login form with userId input
    login_form = None
    for f in soup.find_all("form", attrs={"method": "post"}):
        if f.find("input", attrs={"name": "textUserId"}):
            login_form = f
            break

    if not login_form:
        print("ERROR: Could not find login form on Tama library page")
        return []

    form_action = login_form.get("action", "")
    if form_action.startswith("./"):
        form_action = base_url + "/" + form_action[2:]
    elif not form_action.startswith("http"):
        form_action = base_url + "/" + form_action

    # Step 2: POST login credentials
    login_data = {
        "textUserId": card_number,
        "textPassword": password,
        "buttonLogin": "ログイン",
    }
    resp = session.post(
        form_action,
        data=login_data,
        timeout=15,
        headers={
            "Referer": login_url,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string if soup.title else ""
    if "ログイン" in title and "マイページ" not in title:
        print("ERROR: Login failed for Tama library")
        return []

    # Step 3: Navigate to rental list
    rental_url = base_url + "/rentallist"
    resp = session.get(rental_url, timeout=15, headers={"Referer": resp.url})
    soup = BeautifulSoup(resp.text, "html.parser")

    # Step 4: Parse book items from <section class="infotable"> elements
    sections = soup.find_all("section", class_="infotable")
    for section in sections:
        book = Book(title="", library_name=library_name)

        # Title is in <h3> > <a> > <span>
        h3 = section.find("h3")
        if h3:
            link = h3.find("a")
            if link:
                title_text = link.get_text(strip=True)
                book.title = re.sub(r'\s+', ' ', title_text).strip()
            else:
                title_text = h3.get_text(strip=True)
                # Remove leading number
                title_text = re.sub(r'^\d+\s*', '', title_text)
                book.title = re.sub(r'\s+', ' ', title_text).strip()

        # Metadata is in <div class="item"> > <dl> pairs
        item_div = section.find("div", class_="item")
        if item_div:
            dls = item_div.find_all("dl")
            for dl in dls:
                dt = dl.find("dt")
                dd = dl.find("dd")
                if dt and dd:
                    label = dt.get_text(strip=True)
                    value = dd.get_text(strip=True)
                    if label == "貸出場所":
                        book.publisher = value  # Use publisher field for branch name
                    elif label == "貸出日":
                        book.checkout_date = value
                    elif label == "返却期限":
                        book.due_date = value

        # Check if overdue by comparing due date to today
        if book.due_date:
            try:
                due = datetime.strptime(re.sub(r'[年月]', '/', book.due_date).replace('日', ''), "%Y/%m/%d")
                if due.date() < datetime.now().date():
                    book.is_overdue = True
            except ValueError:
                pass

        if book.title:
            books.append(book)

    return books


def generate_html(all_books: List[Book], output_path: str):
    """Generate a simple HTML page with a table of checked-out books."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    overdue_count = sum(1 for b in all_books if b.is_overdue)
    total = len(all_books)

    rows_html = ""
    for i, book in enumerate(all_books, 1):
        due_class = "due-date overdue" if book.is_overdue else "due-date"
        status_html = '<span class="overdue-badge">延滞</span>' if book.is_overdue else ""
        rows_html += (
            "<tr>"
            "<td>" + str(i) + "</td>"
            "<td>" + book.title + "</td>"
            "<td>" + book.author + "</td>"
            "<td>" + book.publisher + "</td>"
            "<td>" + book.checkout_date + "</td>"
            '<td class="' + due_class + '">' + book.due_date + "</td>"
            "<td>" + status_html + "</td>"
            '<td><span class="library-tag">' + book.library_name + "</span></td>"
            "</tr>\n"
        )

    overdue_card = ""
    if overdue_count > 0:
        overdue_card = (
            '<div class="summary-card overdue">'
            '延滞 <span class="num">' + str(overdue_count) + '</span> 冊'
            '</div>'
        )

    if all_books:
        table_html = (
            '<table><thead><tr>'
            '<th>No.</th><th>タイトル</th><th>著者</th><th>出版社</th>'
            '<th>貸出日</th><th>返却期限</th><th>状態</th><th>図書館</th>'
            '</tr></thead><tbody>'
            + rows_html +
            '</tbody></table>'
        )
    else:
        table_html = '<div class="no-books">現在貸出中の本はありません。</div>'

    html = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>図書館 貸出一覧</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Hiragino Sans','Meiryo','Noto Sans JP',sans-serif;max-width:960px;margin:40px auto;padding:0 20px;background:#f8fafc;color:#1e293b}
h1{font-size:1.6em;color:#1e40af;margin-bottom:8px}
.summary{display:flex;gap:20px;margin-bottom:20px;flex-wrap:wrap}
.summary-card{background:#fff;border-radius:8px;padding:12px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08);font-size:.95em}
.summary-card .num{font-size:1.5em;font-weight:700;color:#1e40af}
.summary-card.overdue .num{color:#dc2626}
.updated{color:#94a3b8;font-size:.85em;margin-bottom:16px}
table{width:100%;border-collapse:collapse;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);border-radius:8px;overflow:hidden;font-size:.92em}
th{background:#1e40af;color:#fff;padding:10px 12px;text-align:left;font-weight:600;white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top}
tr:hover{background:#eff6ff}
tr:last-child td{border-bottom:none}
.overdue-badge{display:inline-block;background:#fef2f2;color:#dc2626;padding:2px 8px;border-radius:4px;font-size:.82em;font-weight:600}
.library-tag{display:inline-block;background:#eff6ff;color:#3b82f6;padding:2px 8px;border-radius:4px;font-size:.82em}
.due-date{white-space:nowrap}
.due-date.overdue{color:#dc2626;font-weight:600}
.no-books{text-align:center;padding:40px;color:#94a3b8;font-size:1.1em;background:#fff;border-radius:8px}
@media(max-width:600px){table{font-size:.82em}th,td{padding:7px 8px}}
</style>
</head>
<body>
<h1>図書館 貸出一覧</h1>
<p class="updated">最終更新: """ + now + """</p>
<div class="summary">
<div class="summary-card">貸出中 <span class="num">""" + str(total) + """</span> 冊</div>
""" + overdue_card + """
</div>
""" + table_html + """
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML output saved to " + output_path)


def main():
    all_books = []

<<<<<<< HEAD
    # Hino City Library
    hino_card = os.environ.get("HINO_LIBRARY_CARD", "91691816")
    hino_password = os.environ.get("HINO_LIBRARY_PASSWORD", "hinohin0123")
    if hino_password:
        print("Scraping 日野市立図書館...")
        try:
            books = scrape_hino_library(hino_card, hino_password)
            print("  Found " + str(len(books)) + " book(s)")
            for i, b in enumerate(books, 1):
                overdue_mark = " [延滞]" if b.is_overdue else ""
                print("  " + str(i) + ". " + b.title + " (" + b.author + ") 返却: " + b.due_date + overdue_mark)
            all_books.extend(books)
        except Exception as e:
            print("  Error: " + str(e))
            import traceback
            traceback.print_exc()
    else:
        print("Skipping 日野市立図書館 (HINO_LIBRARY_PASSWORD not set)")
=======
    # Library configurations: (env_prefix, library_name, base_url, scrape_function)
    libraries = [
        ("HINO", "日野市立図書館", "https://www.lib.city.hino.lg.jp", "winj"),
        ("INAGI", "稲城市立図書館", "https://www1.library.inagi.tokyo.jp", "winj"),
        ("TAMA", "多摩市立図書館", None, "tama"),
    ]
>>>>>>> d468bfefa34adb2c83dedf1eb76c6c94a14e6b39

    for prefix, lib_name, lib_url, lib_type in libraries:
        card = os.environ.get(prefix + "_LIBRARY_CARD", "")
        pw = os.environ.get(prefix + "_LIBRARY_PASSWORD", "")
        if not pw:
            print("Skipping " + lib_name + " (" + prefix + "_LIBRARY_PASSWORD not set)")
            continue
        print("\nScraping " + lib_name + "...")
        try:
            if lib_type == "winj":
                books = scrape_winj_library(lib_url, lib_name, card, pw)
            elif lib_type == "tama":
                books = scrape_tama_library(card, pw)
            else:
                books = []
            print("  Found " + str(len(books)) + " book(s)")
            for i, b in enumerate(books, 1):
                overdue_mark = " [延滞]" if b.is_overdue else ""
                author_part = " (" + b.author + ")" if b.author else ""
                print("  " + str(i) + ". " + b.title + author_part + " 返却: " + b.due_date + overdue_mark)
            all_books.extend(books)
        except Exception as e:
            print("  Error: " + str(e))
            import traceback
            traceback.print_exc()

    output_path = os.environ.get("OUTPUT_PATH", "checkout_list.html")
    generate_html(all_books, output_path)
    print("\nTotal books: " + str(len(all_books)))


if __name__ == "__main__":
    main()
