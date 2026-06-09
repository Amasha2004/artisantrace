# ArtisanTrace 🏺

A web-based traceability platform for handmade products, built with **Flask + SQLAlchemy + Bootstrap 5**.

Artisans file their products with photos and get a unique product code + QR code.  
Buyers can query any product to verify authenticity and view the full filing record.

---

## Features

### Core (Required)
- **Product Filing** — Enter product info, upload 3 images → unique code generated (`AT-XXXXXXXX`)
- **Product Query** — Enter code or scan QR → full filing info displayed
- **Image Storage** — Images saved server-side; only access URLs stored in database
- **Query Logging** — Every query timestamped and persisted to the database

### Extra (Going Beyond)
- **QR Code Generation** — Auto-generated scannable QR code per product, downloadable
- **Admin Login System** — Secure admin panel with Flask-Login + password hashing
- **Search & Filter** — Search by name, artisan, origin, or code; filter by category
- **Query History Dashboard** — Full audit log, top-queried products, daily stats

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3, Flask 3 |
| ORM | Flask-SQLAlchemy (SQLite) |
| Auth | Flask-Login + Werkzeug password hashing |
| Frontend | Bootstrap 5.3, Bootstrap Icons |
| QR Codes | `qrcode` + `Pillow` |
| Templates | Jinja2 |

---

## Project Structure

```
artisantrace/
├── app.py                  # Main Flask app — all routes & models
├── requirements.txt
├── static/
│   ├── uploads/            # Uploaded product images (server-side)
│   └── qrcodes/            # Generated QR code PNGs
├── templates/
│   ├── base.html           # Shared navbar + footer layout
│   ├── public/
│   │   ├── index.html      # Landing page
│   │   ├── query.html      # Query form
│   │   ├── result.html     # Query result / product detail
│   │   └── browse.html     # Browse + search + filter
│   └── admin/
│       ├── login.html      # Admin login
│       ├── dashboard.html  # Stats + top products + recent queries
│       ├── products.html   # All products (searchable table)
│       ├── file_product.html # Filing form with image upload
│       ├── product_detail.html # Detail + QR + query history
│       └── query_logs.html # Full query audit log
└── instance/
    └── artisantrace.db     # SQLite database (auto-created)
```

---

## Setup & Run

```bash
# 1. Clone the repo
git clone https://github.com/Amasha2004/artisantrace.git
cd artisantrace

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

Visit **http://127.0.0.1:5000** in your browser.

**Admin panel:** http://127.0.0.1:5000/admin/login  
Default credentials: `admin` / `admin123` *(change in production)*

---

## Database Schema

```
Product
  id, product_code (unique), name, category, artisan_name, origin,
  description, price, image1_url, image2_url, image3_url, qr_url, filed_at

QueryLog
  id, product_id (FK), product_code, queried_at, ip_address, user_agent

Admin
  id, username (unique), password_hash
```

---

## Screenshots

| Page | Description |
|------|-------------|
| `/` | Landing page with stats and recent products |
| `/browse` | Browse + search + filter all products |
| `/query/<code>` | Product detail with images, QR code, filing info |
| `/admin` | Dashboard with analytics |
| `/admin/products/new` | Filing form with drag-and-drop image preview |
| `/admin/query-logs` | Full audit trail of all queries |

---

## Author

**Amasha** — GitHub: [@Amasha2004](https://github.com/Amasha2004)  
Jingdezhen Ceramic University · Web Application Development · 2026
