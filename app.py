from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests

app = Flask(__name__)
app.secret_key = 'neckhurt123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///musicworld.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='user')

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    describe = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Float, nullable=False)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author = db.Column(db.String(100))
    text = db.Column(db.Text)
    approved = db.Column(db.Boolean, default=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(100))
    items = db.relationship('OrderItem', backref='order', cascade="all, delete-orphan")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    item_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Integer)

def get_exchange_rates():
    try:
        response = requests.get('https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5')
        data = response.json()
        rates = {}
        for item in data:
            if item['ccy'] in ['USD', 'EUR']:
                rates[item['ccy']] = {
                    'buy': float(item['buy']),
                    'sale': float(item['sale'])
                }
        return rates
    except Exception as e:
        print("Помилка отримання курсу валют:", e)
        return {}

def is_logged_in():
    return 'user' in session

def is_admin():
    return session.get('role') == 'admin'

@app.context_processor
def inject_user_and_rates():
    rates = get_exchange_rates()
    return dict(
        logged_in=is_logged_in(),
        is_admin=is_admin(),
        exchange_rates=rates
    )

@app.context_processor
def inject_user():
    return dict(logged_in=is_logged_in(), is_admin=is_admin())

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/items')
def items():
    all_items = Item.query.all()
    return render_template('items.html', items=all_items)

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        if not email or not password or not confirm:
            return render_template('register.html', error="Будь ласка, заповніть усі поля")
        if password != confirm:
            return render_template('register.html', error="Паролі не співпадають")
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error="Користувач з таким email вже існує")
        hashed_password = generate_password_hash(password)
        user = User(email=email, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash("Реєстрація успішна! Увійдіть у свій акаунт")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and (check_password_hash(user.password, password) or user.password == password):
            session['user'] = user.email
            session['role'] = user.role
            flash('Ви увійшли в систему')
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Неправильний email або пароль')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Ви вийшли з системи')
    return redirect(url_for('index'))

@app.route('/feedbacks')
def feedbacks():
    feedbacks = Feedback.query.all() if is_admin() else Feedback.query.filter_by(approved=True).all()
    return render_template('feedbacks.html', feedbacks=feedbacks)

@app.route('/add_feedback', methods=['GET', 'POST'])
def add_feedback():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    if request.method == 'POST':
        text = request.form.get('text')
        if text:
            fb = Feedback(author=session['user'], text=text, approved=False)
            db.session.add(fb)
            db.session.commit()
            flash('Відгук додано та очікує схвалення')
            return redirect(url_for('feedbacks'))
    return render_template('add_feedback.html')

@app.route('/orders', methods=['GET', 'POST'])
def orders():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    items = Item.query.all()
    if request.method == 'POST':
        item_id = int(request.form.get('item_id'))
        quantity = int(request.form.get('quantity'))
        item = Item.query.get(item_id)
        if not item or quantity < 1:
            flash('Некоректні дані')
            return redirect(url_for('orders'))
        cart = session.get('cart', {})
        cart[str(item_id)] = cart.get(str(item_id), 0) + quantity
        session['cart'] = cart
        flash(f'Додано {quantity} шт. "{item.name}" у кошик')
        return redirect(url_for('orders'))
    return render_template('orders.html', items=items)

@app.route('/cart', methods=['GET', 'POST'])
def cart():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    for item_id, qty in cart.items():
        item = Item.query.get(int(item_id))
        if item:
            subtotal = item.price * qty
            total += subtotal
            cart_items.append({'id': item.id, 'name': item.name, 'price': item.price, 'quantity': qty, 'total_price': subtotal})
    if request.method == 'POST' and cart_items:
        order = Order(user_email=session['user'])
        db.session.add(order)
        db.session.flush()
        for item in cart_items:
            db.session.add(OrderItem(order_id=order.id, item_name=item['name'], quantity=item['quantity'], price=item['price']))
        db.session.commit()
        session.pop('cart', None)
        flash('Замовлення оформлено. Дякуємо!')
        return redirect(url_for('index'))
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/admin/feedbacks')
def admin_feedbacks():
    if not is_admin(): return redirect(url_for('login'))
    return render_template('admin_feedbacks.html', feedbacks=Feedback.query.all())

@app.route('/admin/feedbacks/<int:fb_id>/approve')
def approve_feedback(fb_id):
    if not is_admin(): return redirect(url_for('login'))
    fb = Feedback.query.get_or_404(fb_id)
    fb.approved = True
    db.session.commit()
    flash('Схвалено')
    return redirect(url_for('admin_feedbacks'))

@app.route('/admin/feedbacks/<int:fb_id>/reject')
def reject_feedback(fb_id):
    if not is_admin(): return redirect(url_for('login'))
    db.session.delete(Feedback.query.get_or_404(fb_id))
    db.session.commit()
    flash('Видалено')
    return redirect(url_for('admin_feedbacks'))

@app.route('/admin/items')
def admin_items():
    if not is_admin(): return redirect(url_for('login'))
    return render_template('admin_items.html', items=Item.query.all())

@app.route('/admin/items/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    if not is_admin(): return redirect(url_for('login'))
    item = Item.query.get_or_404(item_id)
    if request.method == 'POST':
        item.name = request.form.get('name')
        item.describe = request.form.get('describe')
        item.price = float(request.form.get('price'))
        db.session.commit()
        flash('Оновлено')
        return redirect(url_for('admin_items'))
    return render_template('edit_item.html', item=item)

@app.route('/admin/items/delete/<int:item_id>')
def delete_item(item_id):
    if not is_admin(): return redirect(url_for('login'))
    db.session.delete(Item.query.get_or_404(item_id))
    db.session.commit()
    flash('Товар видалено')
    return redirect(url_for('admin_items'))

@app.route('/admin/items/add', methods=['GET', 'POST'])
def add_item():
    if not is_admin(): return redirect(url_for('login'))
    if request.method == 'POST':
        new_item = Item(
            name=request.form.get('name'),
            describe=request.form.get('describe'),
            price=float(request.form.get('price')),
        )
        db.session.add(new_item)
        db.session.commit()
        flash('Додано')
        return redirect(url_for('admin_items'))
    return render_template('add_item.html')

@app.route('/admin/orders/delete/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    if not is_admin():
        return redirect(url_for('login'))
    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    flash('Замовлення видалено')
    return redirect(url_for('admin_orders'))

@app.route('/admin/orders')
def admin_orders():
    if not is_admin(): return redirect(url_for('login'))
    return render_template('admin_orders.html', orders=Order.query.all())

with app.app_context():
    db.create_all()
    if not User.query.first():
        db.session.add_all([
            User(email='admin@technoservice.ua', password='admin123', role='admin')
        ])
    if not Item.query.first():
        db.session.add_all([
            Item(name='Gibson - 1957 Les Paul', describe='Электрогітара', price=25000),
            Item(name='Roland TD-02KV', describe='Ударна установка', price=17000),
            Item(name='YAMAHA PSR-F52', describe='Синтезатор', price=15000),
        ])
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)

