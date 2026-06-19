from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
import hashlib
import json
import qrcode
from io import BytesIO
from datetime import datetime
from functools import wraps
from web3 import Web3
import json as json_module

# Connect to Ganache blockchain
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
blockchain_account = w3.eth.accounts[0]

# Load smart contract
try:
    with open('contract_info.json', 'r') as f:
        contract_info = json_module.load(f)
    artisan_contract = w3.eth.contract(
        address=contract_info['address'],
        abi=contract_info['abi']
    )
    BLOCKCHAIN_ENABLED = True
    print('✓ Smart contract connected!')
except:
    BLOCKCHAIN_ENABLED = False
    print('⚠ Smart contract not found — blockchain disabled')

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, send_from_directory, abort, session)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'artisantrace-secret-key-change-in-prod'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///artisantrace.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['QR_FOLDER'] = os.path.join(app.root_path, 'static', 'qrcodes')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['QR_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'
login_manager.login_message = 'Please log in to access the admin panel.'
login_manager.login_message_category = 'warning'

# ── Models ────────────────────────────────────────────────────────────────────

class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class Buyer(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    joined_at     = db.Column(db.DateTime, default=datetime.utcnow)
    queries       = db.relationship('QueryLog', backref='buyer', lazy=True)
    saved_products = db.relationship('SavedProduct', backref='buyer',
                                     lazy=True, cascade='all, delete-orphan')

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)


class SavedProduct(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    buyer_id   = db.Column(db.Integer, db.ForeignKey('buyer.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    saved_at   = db.Column(db.DateTime, default=datetime.utcnow)
    product    = db.relationship('Product', backref='saved_by')


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    artisan_name = db.Column(db.String(100), nullable=False)
    origin = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    image1_url = db.Column(db.String(300), nullable=False)
    image2_url = db.Column(db.String(300), nullable=False)
    image3_url = db.Column(db.String(300), nullable=False)
    qr_url = db.Column(db.String(300))
    filed_at = db.Column(db.DateTime, default=datetime.utcnow)
    tx_hash = db.Column(db.String(100))  # Ethereum transaction hash
    queries = db.relationship('QueryLog', backref='product', lazy=True,
                              cascade='all, delete-orphan')

    @property
    def query_count(self):
        return len(self.queries)


class QueryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product_code = db.Column(db.String(20), nullable=False)
    queried_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(300))
    buyer_id = db.Column(db.Integer, db.ForeignKey('buyer.id'), nullable=True)
    buyer_name = db.Column(db.String(100), nullable=True)


class Block(db.Model):
    """One block per filed product — forms the traceability blockchain."""
    id            = db.Column(db.Integer, primary_key=True)
    block_index   = db.Column(db.Integer, unique=True, nullable=False)
    timestamp     = db.Column(db.String(40), nullable=False)
    product_code  = db.Column(db.String(20), nullable=False)
    product_id    = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    data          = db.Column(db.Text, nullable=False)   # JSON snapshot of product
    previous_hash = db.Column(db.String(64), nullable=False)
    block_hash    = db.Column(db.String(64), nullable=False)

    product = db.relationship('Product', backref=db.backref('block', uselist=False))

    def compute_hash(self):
        block_str = json.dumps({
            'index':         self.block_index,
            'timestamp':     self.timestamp,
            'product_code':  self.product_code,
            'data':          self.data,
            'previous_hash': self.previous_hash,
        }, sort_keys=True)
        return hashlib.sha256(block_str.encode()).hexdigest()

    @property
    def is_valid(self):
        return self.block_hash == self.compute_hash()



@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Admin, int(user_id))

def get_current_buyer():
    """Get the currently logged-in buyer from session."""
    buyer_id = session.get('buyer_id')
    if buyer_id:
        return db.session.get(Buyer, buyer_id)
    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_product_code():
    """AT-XXXXXXXX — 8 hex chars, guaranteed unique."""
    while True:
        code = 'AT-' + uuid.uuid4().hex[:8].upper()
        if not Product.query.filter_by(product_code=code).first():
            return code


def generate_qr(product_code):
    """Generate QR code PNG and save it; return its URL path."""
    query_url = url_for('public_query_result', code=product_code, _external=True)
    img = qrcode.make(query_url)
    filename = f'qr_{product_code}.png'
    path = os.path.join(app.config['QR_FOLDER'], filename)
    img.save(path)
    return url_for('static', filename=f'qrcodes/{filename}')


def save_image(file_obj, prefix='img'):
    """Save an uploaded image; return its URL path."""
    ext = file_obj.filename.rsplit('.', 1)[1].lower()
    filename = f"{prefix}_{uuid.uuid4().hex[:10]}.{ext}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file_obj.save(path)
    return url_for('static', filename=f'uploads/{filename}')




# ── Blockchain helpers ────────────────────────────────────────────────────────

def create_genesis_block():
    """Create the very first block (index 0) if chain is empty."""
    if Block.query.count() == 0:
        genesis = Block(
            block_index=0,
            timestamp=datetime.utcnow().isoformat(),
            product_code='GENESIS',
            product_id=1,   # placeholder — reassigned after first real product
            data=json.dumps({'message': 'ArtisanTrace Genesis Block'}),
            previous_hash='0' * 64,
        )
        genesis.block_hash = genesis.compute_hash()
        # Genesis block does not need a real product_id FK, so we bypass FK here
        # by inserting directly; handled via special-case in template
        db.session.execute(
            db.text(
                "INSERT INTO block (block_index, timestamp, product_code, product_id, data, previous_hash, block_hash) "
                "VALUES (:bi, :ts, :pc, :pid, :d, :ph, :bh)"
            ),
            dict(bi=0, ts=genesis.timestamp, pc='GENESIS', pid=0,
                 d=genesis.data, ph=genesis.previous_hash, bh=genesis.block_hash)
        )
        db.session.commit()


def add_product_to_chain(product):
    """Mine a new block for the given product and append to chain."""
    last = Block.query.order_by(Block.block_index.desc()).first()
    previous_hash = last.block_hash if last else '0' * 64
    next_index    = (last.block_index + 1) if last else 1

    data_snapshot = json.dumps({
        'product_code': product.product_code,
        'name':         product.name,
        'category':     product.category,
        'artisan_name': product.artisan_name,
        'origin':       product.origin,
        'price':        product.price,
        'filed_at':     product.filed_at.isoformat(),
    }, sort_keys=True)

    block = Block(
        block_index=next_index,
        timestamp=datetime.utcnow().isoformat(),
        product_code=product.product_code,
        product_id=product.id,
        data=data_snapshot,
        previous_hash=previous_hash,
    )
    block.block_hash = block.compute_hash()
    db.session.add(block)
    db.session.commit()
    return block


def verify_chain():
    """Walk every block and check hash integrity. Returns (is_valid, results)."""
    blocks = Block.query.order_by(Block.block_index).all()
    results = []
    chain_valid = True

    for i, block in enumerate(blocks):
        hash_ok = block.block_hash == block.compute_hash()
        link_ok = True
        if i > 0:
            link_ok = block.previous_hash == blocks[i-1].block_hash
        valid = hash_ok and link_ok
        if not valid:
            chain_valid = False
        results.append({
            'block':     block,
            'hash_ok':   hash_ok,
            'link_ok':   link_ok,
            'valid':     valid,
        })

    return chain_valid, results

# ── Public routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    total_products = Product.query.count()
    total_queries = QueryLog.query.count()
    recent = Product.query.order_by(Product.filed_at.desc()).limit(6).all()
    categories = db.session.query(Product.category,
                                  db.func.count(Product.id)).group_by(Product.category).all()
    return render_template('public/index.html',
                           total_products=total_products,
                           total_queries=total_queries,
                           recent=recent,
                           categories=categories)


@app.route('/query', methods=['GET', 'POST'])
def public_query():
    if request.method == 'POST':
        code = request.form.get('product_code', '').strip().upper()
        if not code:
            flash('Please enter a product code.', 'warning')
            return redirect(url_for('public_query'))
        return redirect(url_for('public_query_result', code=code))
    return render_template('public/query.html')


@app.route('/query/<code>')
def public_query_result(code):
    code = code.strip().upper()
    product = Product.query.filter_by(product_code=code).first()
    if not product:
        flash(f'No product found with code "{code}".', 'danger')
        return render_template('public/query.html', not_found=True, searched_code=code)

    # Get buyer once at the top
    buyer = get_current_buyer()

    # Log this query — include buyer info if logged in
    log = QueryLog(
        product_id=product.id,
        product_code=code,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:300],
        buyer_id=buyer.id if buyer else None,
        buyer_name=buyer.name if buyer else None,
    )
    db.session.add(log)
    db.session.commit()

    # Check if buyer saved this product
    is_saved = False
    if buyer:
        is_saved = SavedProduct.query.filter_by(
            buyer_id=buyer.id, product_id=product.id).first() is not None

    return render_template('public/result.html',
                           product=product,
                           buyer=buyer,
                           is_saved=is_saved)


@app.route('/browse')
def browse():
    q = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Product.query
    if q:
        query = query.filter(
            db.or_(Product.name.ilike(f'%{q}%'),
                   Product.artisan_name.ilike(f'%{q}%'),
                   Product.origin.ilike(f'%{q}%'),
                   Product.product_code.ilike(f'%{q}%'))
        )
    if category:
        query = query.filter_by(category=category)

    products = query.order_by(Product.filed_at.desc()).paginate(page=page, per_page=9)
    categories = db.session.query(Product.category).distinct().all()
    return render_template('public/browse.html',
                           products=products, q=q,
                           selected_category=category,
                           categories=[c[0] for c in categories])


# ── Admin routes ──────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin, remember=True)
            flash('Welcome back!', 'success')
            return redirect(request.args.get('next') or url_for('admin_dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('admin/login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


@app.route('/admin')
@login_required
def admin_dashboard():
    total_products = Product.query.count()
    total_queries = QueryLog.query.count()
    today = datetime.utcnow().date()
    queries_today = QueryLog.query.filter(
        db.func.date(QueryLog.queried_at) == today
    ).count()
    top_products = db.session.query(
        Product, db.func.count(QueryLog.id).label('qcount')
    ).join(QueryLog, isouter=True).group_by(Product.id)\
     .order_by(db.desc('qcount')).limit(5).all()
    recent_logs = QueryLog.query.order_by(QueryLog.queried_at.desc()).limit(10).all()
    categories = db.session.query(Product.category,
                                  db.func.count(Product.id)).group_by(Product.category).all()
    return render_template('admin/dashboard.html',
                           total_products=total_products,
                           total_queries=total_queries,
                           queries_today=queries_today,
                           top_products=top_products,
                           recent_logs=recent_logs,
                           categories=categories)


@app.route('/admin/products')
@login_required
def admin_products():
    q = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    page = request.args.get('page', 1, type=int)
    query = Product.query
    if q:
        query = query.filter(
            db.or_(Product.name.ilike(f'%{q}%'),
                   Product.artisan_name.ilike(f'%{q}%'),
                   Product.product_code.ilike(f'%{q}%'))
        )
    if category:
        query = query.filter_by(category=category)
    products = query.order_by(Product.filed_at.desc()).paginate(page=page, per_page=10)
    categories = db.session.query(Product.category).distinct().all()
    return render_template('admin/products.html',
                           products=products, q=q,
                           selected_category=category,
                           categories=[c[0] for c in categories])


@app.route('/admin/products/new', methods=['GET', 'POST'])
@login_required
def admin_file_product():
    if request.method == 'POST':
        # Validate images
        images = [request.files.get(f'image{i}') for i in range(1, 4)]
        for i, img in enumerate(images, 1):
            if not img or img.filename == '':
                flash(f'Image {i} is required.', 'danger')
                return render_template('admin/file_product.html')
            if not allowed_file(img.filename):
                flash(f'Image {i} must be PNG/JPG/GIF/WEBP.', 'danger')
                return render_template('admin/file_product.html')

        try:
            price = float(request.form['price'])
        except ValueError:
            flash('Price must be a number.', 'danger')
            return render_template('admin/file_product.html')

        code = generate_product_code()
        img_urls = [save_image(img, prefix=f'img{i+1}') for i, img in enumerate(images)]

        product = Product(
            product_code=code,
            name=request.form['name'].strip(),
            category=request.form['category'].strip(),
            artisan_name=request.form['artisan_name'].strip(),
            origin=request.form['origin'].strip(),
            description=request.form['description'].strip(),
            price=price,
            image1_url=img_urls[0],
            image2_url=img_urls[1],
            image3_url=img_urls[2],
        )
        db.session.add(product)
        db.session.flush()  # get product.id before QR generation

        # Generate QR code
        product.qr_url = generate_qr(code)
        db.session.commit()

        # Add product to our DB blockchain
        add_product_to_chain(product)

        # Also record on Ethereum blockchain via Ganache
        if BLOCKCHAIN_ENABLED:
            try:
                tx_hash = artisan_contract.functions.fileProduct(
                    product.product_code,
                    product.name,
                    product.category,
                    product.artisan_name,
                    product.origin
                ).transact({'from': blockchain_account})
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                product.tx_hash = receipt.transactionHash.hex()
                db.session.commit()
                print(f'✓ Product filed on Ethereum: {product.tx_hash}')
            except Exception as e:
                print(f'⚠ Ethereum filing failed: {e}')

        flash(f'Product filed successfully! Code: {code} — Block added to chain ⛓️', 'success')
        return redirect(url_for('admin_product_detail', product_id=product.id))

    return render_template('admin/file_product.html')


@app.route('/admin/products/<int:product_id>')
@login_required
def admin_product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    logs = QueryLog.query.filter_by(product_id=product_id)\
                         .order_by(QueryLog.queried_at.desc()).all()
    return render_template('admin/product_detail.html', product=product, logs=logs)


@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@login_required
def admin_delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f'Product "{name}" deleted.', 'info')
    return redirect(url_for('admin_products'))


@app.route('/admin/query-logs')
@login_required
def admin_query_logs():
    page = request.args.get('page', 1, type=int)
    logs = QueryLog.query.order_by(QueryLog.queried_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/query_logs.html', logs=logs)



@app.route('/blockchain')
def blockchain_explorer():
    """Public blockchain explorer — anyone can verify the chain."""
    chain_valid, results = verify_chain()
    total_blocks = Block.query.count()
    return render_template('public/blockchain.html',
                           chain_valid=chain_valid,
                           results=results,
                           total_blocks=total_blocks)


@app.route('/admin/blockchain')
@login_required
def admin_blockchain():
    """Admin blockchain view with full details."""
    chain_valid, results = verify_chain()
    total_blocks = Block.query.count()
    return render_template('admin/blockchain.html',
                           chain_valid=chain_valid,
                           results=results,
                           total_blocks=total_blocks)
@app.route('/admin/statistics')
@login_required
def admin_statistics():
    return render_template('admin/statistics.html')

# ── Buyer routes ──────────────────────────────────────────────────────────────

@app.route('/buyer/register', methods=['GET', 'POST'])
def buyer_register():
    if get_current_buyer():
        return redirect(url_for('buyer_dashboard'))
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('buyer/register.html')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('buyer/register.html')
        if Buyer.query.filter_by(email=email).first():
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('buyer_login'))

        buyer = Buyer(name=name, email=email)
        buyer.set_password(password)
        db.session.add(buyer)
        db.session.commit()

        session['buyer_id'] = buyer.id
        flash(f'Welcome, {name}! Your account has been created.', 'success')
        return redirect(url_for('buyer_dashboard'))

    return render_template('buyer/register.html')


@app.route('/buyer/login', methods=['GET', 'POST'])
def buyer_login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        buyer    = Buyer.query.filter_by(email=email).first()

        if buyer and buyer.check_password(password):
            session.permanent = True
            session['buyer_id'] = int(buyer.id)
            print(f'✓ Buyer logged in: id={buyer.id} name={buyer.name}')
            flash(f'Welcome back, {buyer.name}!', 'success')
            return redirect(url_for('buyer_dashboard'))
        flash('Invalid email or password.', 'danger')

    return render_template('buyer/login.html')


@app.route('/buyer/logout')
def buyer_logout():
    session.pop('buyer_id', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


@app.route('/buyer/dashboard')
def buyer_dashboard():
    buyer_id = session.get('buyer_id')
    print(f'Dashboard session buyer_id: {buyer_id}')

    if not buyer_id:
        flash('Please login first.', 'warning')
        return redirect(url_for('buyer_login'))

    buyer = Buyer.query.filter_by(id=int(buyer_id)).first()
    print(f'Dashboard buyer found: {buyer}')

    if not buyer:
        session.clear()
        flash('Session expired. Please login again.', 'warning')
        return redirect(url_for('buyer_login'))

    recent_queries = QueryLog.query.filter_by(buyer_id=buyer.id)\
                             .order_by(QueryLog.queried_at.desc()).limit(10).all()
    saved = SavedProduct.query.filter_by(buyer_id=buyer.id)\
                              .order_by(SavedProduct.saved_at.desc()).all()
    return render_template('buyer/dashboard.html',
                           buyer=buyer,
                           recent_queries=recent_queries,
                           saved=saved)


@app.route('/buyer/profile', methods=['GET', 'POST'])
def buyer_profile():
    buyer = get_current_buyer()
    if not buyer:
        return redirect(url_for('buyer_login'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        current_pw  = request.form.get('current_password', '')
        new_pw      = request.form.get('new_password', '')

        if name:
            buyer.name = name
        if current_pw and new_pw:
            if buyer.check_password(current_pw):
                buyer.set_password(new_pw)
                flash('Password updated successfully.', 'success')
            else:
                flash('Current password is incorrect.', 'danger')
                return render_template('buyer/profile.html', buyer=buyer)

        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('buyer_profile'))

    return render_template('buyer/profile.html', buyer=buyer)


@app.route('/buyer/save/<int:product_id>', methods=['POST'])
def buyer_save_product(product_id):
    buyer = get_current_buyer()
    if not buyer:
        flash('Please login to save products.', 'warning')
        return redirect(url_for('buyer_login'))

    already = SavedProduct.query.filter_by(
        buyer_id=buyer.id, product_id=product_id).first()
    if already:
        db.session.delete(already)
        db.session.commit()
        flash('Product removed from saved items.', 'info')
    else:
        saved = SavedProduct(buyer_id=buyer.id, product_id=product_id)
        db.session.add(saved)
        db.session.commit()
        flash('Product saved successfully!', 'success')

    return redirect(request.referrer or url_for('index'))


@app.route('/buyer/history')
def buyer_history():
    buyer = get_current_buyer()
    if not buyer:
        return redirect(url_for('buyer_login'))
    page = request.args.get('page', 1, type=int)
    logs = QueryLog.query.filter_by(buyer_id=buyer.id)\
                         .order_by(QueryLog.queried_at.desc())\
                         .paginate(page=page, per_page=15)
    return render_template('buyer/history.html', buyer=buyer, logs=logs)


@app.route('/buyer/saved')
def buyer_saved():
    buyer = get_current_buyer()
    if not buyer:
        return redirect(url_for('buyer_login'))
    saved = SavedProduct.query.filter_by(buyer_id=buyer.id)\
                              .order_by(SavedProduct.saved_at.desc()).all()
    return render_template('buyer/saved.html', buyer=buyer, saved=saved)

# ── REST API ──────────────────────────────────────────────────────────────────

@app.route('/api/products', methods=['GET'])
def api_products():
    """Return all products as JSON. Optional ?category= and ?q= filters."""
    q        = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    query    = Product.query
    if q:
        query = query.filter(
            db.or_(Product.name.ilike(f'%{q}%'),
                   Product.artisan_name.ilike(f'%{q}%'),
                   Product.origin.ilike(f'%{q}%'),
                   Product.product_code.ilike(f'%{q}%'))
        )
    if category:
        query = query.filter_by(category=category)
    products = query.order_by(Product.filed_at.desc()).all()
    return {
        'status':  'ok',
        'count':   len(products),
        'products': [{
            'product_code': p.product_code,
            'name':         p.name,
            'category':     p.category,
            'artisan_name': p.artisan_name,
            'origin':       p.origin,
            'price':        p.price,
            'filed_at':     p.filed_at.isoformat(),
            'query_count':  p.query_count,
            'image1_url':   p.image1_url,
            'qr_url':       p.qr_url,
        } for p in products]
    }


@app.route('/api/products/<code>', methods=['GET'])
def api_product_detail(code):
    """Return a single product by product code."""
    product = Product.query.filter_by(product_code=code.upper()).first()
    if not product:
        return {'status': 'error', 'message': f'Product {code} not found'}, 404
    return {
        'status': 'ok',
        'product': {
            'product_code': product.product_code,
            'name':         product.name,
            'category':     product.category,
            'artisan_name': product.artisan_name,
            'origin':       product.origin,
            'description':  product.description,
            'price':        product.price,
            'filed_at':     product.filed_at.isoformat(),
            'query_count':  product.query_count,
            'image1_url':   product.image1_url,
            'image2_url':   product.image2_url,
            'image3_url':   product.image3_url,
            'qr_url':       product.qr_url,
        }
    }


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Return dashboard statistics as JSON — used by charts."""
    from datetime import timedelta

    # Products per category
    categories = db.session.query(
        Product.category, db.func.count(Product.id)
    ).group_by(Product.category).all()

    # Queries per day (last 7 days)
    today = datetime.utcnow().date()
    daily_queries = []
    for i in range(6, -1, -1):
        day   = today - timedelta(days=i)
        count = QueryLog.query.filter(
            db.func.date(QueryLog.queried_at) == day
        ).count()
        daily_queries.append({'date': str(day), 'count': count})

    # Top 5 most queried products
    top = db.session.query(
        Product.name, Product.product_code,
        db.func.count(QueryLog.id).label('qcount')
    ).join(QueryLog, isouter=True).group_by(Product.id)\
     .order_by(db.desc('qcount')).limit(5).all()

    return {
        'status':        'ok',
        'total_products': Product.query.count(),
        'total_queries':  QueryLog.query.count(),
        'total_blocks':   Block.query.count(),
        'categories': [{'name': c[0], 'count': c[1]} for c in categories],
        'daily_queries':  daily_queries,
        'top_products': [{'name': t[0], 'code': t[1], 'queries': t[2] or 0} for t in top],
    }


@app.route('/api/blockchain', methods=['GET'])
def api_blockchain():
    """Return blockchain status and all blocks as JSON."""
    chain_valid, results = verify_chain()
    return {
        'status':       'ok',
        'chain_valid':  chain_valid,
        'total_blocks': Block.query.count(),
        'blocks': [{
            'index':         r['block'].block_index,
            'product_code':  r['block'].product_code,
            'timestamp':     r['block'].timestamp,
            'block_hash':    r['block'].block_hash,
            'previous_hash': r['block'].previous_hash,
            'hash_valid':    r['hash_ok'],
            'link_valid':    r['link_ok'],
        } for r in results]
    }

# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# ── Init DB ───────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        if not Admin.query.filter_by(username='admin').first():
            a = Admin(username='admin')
            a.set_password('admin123')
            db.session.add(a)
            db.session.commit()
            print('✓ Default admin created: admin / admin123')
        create_genesis_block()


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
