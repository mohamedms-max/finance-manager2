# app.py
from flask import Flask, request, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder='static', static_url_path='/')
app.config['SECRET_KEY'] = 'change_this_secret_in_prod_please'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)  # 'income' or 'expense'
    category = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.String(20), nullable=False)
    desc = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Helpers
def get_current_user():
    username = session.get('username')
    if not username:
        return None
    return User.query.filter_by(username=username).first()

# Static landing
@app.route('/')
def landing():
    return app.send_static_file('landing.html')

# Auth API
@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({'error':'username and password required'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error':'user exists'}), 400
    u = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(u)
    db.session.commit()
    return jsonify({'ok':True}), 201

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    u = User.query.filter_by(username=username).first()
    if not u or not check_password_hash(u.password_hash, password):
        return jsonify({'error':'invalid credentials'}), 401
    session.permanent = True
    session['username'] = username
    return jsonify({'ok':True, 'username': username})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('username', None)
    return jsonify({'ok':True})

@app.route('/api/me', methods=['GET'])
def api_me():
    u = get_current_user()
    if not u:
        return jsonify({'logged_in': False}), 200
    return jsonify({'logged_in': True, 'username': u.username})

# Categories API
@app.route('/api/categories', methods=['GET','POST'])
def api_categories():
    u = get_current_user()
    if not u:
        return jsonify({'error':'not authenticated'}), 401
    if request.method == 'GET':
        cats = Category.query.filter((Category.user_id==None) | (Category.user_id==u.id)).all()
        out = [{'id': c.id, 'name': c.name, 'user_id': c.user_id} for c in cats]
        return jsonify({'categories': out})
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error':'name required'}), 400
    c = Category(name=name, user_id=u.id)
    db.session.add(c)
    db.session.commit()
    return jsonify({'ok':True, 'id': c.id, 'name': c.name}), 201

@app.route('/api/categories/<int:cat_id>', methods=['DELETE'])
def api_delete_category(cat_id):
    u = get_current_user()
    if not u:
        return jsonify({'error':'not authenticated'}), 401
    c = Category.query.get(cat_id)
    if not c:
        return jsonify({'error':'not found'}), 404
    if c.user_id is not None and c.user_id != u.id:
        return jsonify({'error':'forbidden'}), 403
    db.session.delete(c)
    db.session.commit()
    return jsonify({'ok':True})

# Transactions API
@app.route('/api/transactions', methods=['GET','POST'])
def api_transactions():
    u = get_current_user()
    if not u:
        return jsonify({'error':'not authenticated'}), 401
    if request.method == 'GET':
        txs = Transaction.query.filter_by(user_id=u.id).order_by(Transaction.date.desc()).all()
        out = []
        for t in txs:
            out.append({
                'id': t.id,
                'type': t.type,
                'category': t.category,
                'amount': t.amount,
                'date': t.date,
                'desc': t.desc
            })
        return jsonify({'transactions': out})
    data = request.json or {}
    ttype = data.get('type')
    category = data.get('category')
    amount = data.get('amount')
    date = data.get('date')
    desc = data.get('desc','')
    try:
        amount = float(amount)
    except:
        return jsonify({'error':'invalid amount'}), 400
    if ttype not in ('income','expense') or not category or not date:
        return jsonify({'error':'invalid data'}), 400
    t = Transaction(type=ttype, category=category, amount=amount, date=date, desc=desc, user_id=u.id)
    db.session.add(t)
    db.session.commit()
    return jsonify({'ok':True, 'id': t.id}), 201

@app.route('/api/transactions/<int:tx_id>', methods=['DELETE'])
def api_delete_tx(tx_id):
    u = get_current_user()
    if not u:
        return jsonify({'error':'not authenticated'}), 401
    t = Transaction.query.get(tx_id)
    if not t or t.user_id != u.id:
        return jsonify({'error':'not found'}), 404
    db.session.delete(t)
    db.session.commit()
    return jsonify({'ok':True})

# Stats API
@app.route('/api/stats', methods=['GET'])
def api_stats():
    u = get_current_user()
    if not u:
        return jsonify({'error':'not authenticated'}), 401
    txs = Transaction.query.filter_by(user_id=u.id).all()
    income = sum(t.amount for t in txs if t.type=='income')
    expense = sum(t.amount for t in txs if t.type=='expense')
    return jsonify({
        'income': round(income,2),
        'expense': round(expense,2),
        'balance': round(income - expense,2)
    })

# Serve static files
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)


if __name__ == '__main__':
    # create DB if missing -- ensure we run this inside app context
    db_path = os.path.join(BASE_DIR, 'data.db')
    with app.app_context():
        if not os.path.exists(db_path):
            db.create_all()
            # seed some default categories (global)
            db.session.add(Category(name='Зарплата', user_id=None))
            db.session.add(Category(name='Продукты', user_id=None))
            db.session.add(Category(name='Транспорт', user_id=None))
            db.session.commit()
            print("Initialized database.")
    # Run Flask app
    # On Windows PowerShell, just run: python app.py
    # If you prefer 'flask run', set FLASK_APP=app and use 'flask run' (but ensure debug/reloader behavior)
    app.run(debug=True)
