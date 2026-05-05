# Library Book Checkout Scraper

Scrapes checked-out books from Japanese public library OPAC systems and generates a simple HTML table page.

## Supported Libraries

- Hino City Library (日野市立図書館)

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
export HINO_LIBRARY_PASSWORD="your_password"
python scraper.py
```

The script will generate `checkout_list.html` with a table of all currently checked-out books.

## Output

The HTML page shows:
- Book title, author, publisher
- Checkout date and due date
- Overdue status (延滞)
- Library name
