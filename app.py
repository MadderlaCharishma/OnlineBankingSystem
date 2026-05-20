from flask import Flask, render_template, request, redirect, session
import mysql.connector
from datetime import datetime
import random

app = Flask(__name__)
app.secret_key = "banksecret"

print("BANK SYSTEM STARTED")


# ---------------- DATABASE CONNECTION ----------------
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Password",
    database="smartbankdb"
)

cursor = db.cursor()


# ---------------- HOME ----------------
@app.route('/')
def home():
    return render_template('index.html')


# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        # CHECK EXISTING USER
        cursor.execute(
            "SELECT * FROM users WHERE username=%s",
            (username,)
        )

        existing_user = cursor.fetchone()

        if existing_user:
            return "❌ Username already exists"

        # GENERATE ACCOUNT NUMBER
        account_number = random.randint(10000000, 99999999)

        # INSERT USER
        cursor.execute("""
        INSERT INTO users
        (username,password,balance,role,status,last_login,account_number)
        VALUES(%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            username,
            password,
            0,
            'user',
            'active',
            datetime.now(),
            account_number
        ))

        db.commit()

        return redirect('/login')

    return render_template('register.html')


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password)
        )

        user = cursor.fetchone()

        if user:

            # ACCOUNT BLOCK CHECK
            if user[5] == 'blocked':
                return "❌ Account Frozen By Admin"

            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[4]

            # UPDATE LAST LOGIN
            cursor.execute(
                "UPDATE users SET last_login=%s WHERE id=%s",
                (datetime.now(), user[0])
            )

            # LOGIN LOG
            cursor.execute(
                "INSERT INTO login_logs(user_id,username) VALUES(%s,%s)",
                (user[0], user[1])
            )

            db.commit()

            # ADMIN LOGIN
            if user[4] == 'admin':
                return redirect('/admin')

            return redirect('/dashboard')

        else:
            return "❌ Invalid Username or Password"

    return render_template('login.html')


# ---------------- USER DASHBOARD ----------------
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    # ---------------- DEPOSIT / WITHDRAW ----------------
    if request.method == 'POST':

        action = request.form['action']
        amount = float(request.form['amount'])

        # ---------------- DEPOSIT ----------------
        if action == 'deposit':

            cursor.execute(
                "UPDATE users SET balance=balance+%s WHERE id=%s",
                (amount, user_id)
            )

            cursor.execute("""
            INSERT INTO transactions
            (user_id,type,amount,sender,receiver)
            VALUES(%s,%s,%s,%s,%s)
            """,
            (
                user_id,
                'Deposit',
                amount,
                session['username'],
                session['username']
            ))

            db.commit()

        # ---------------- WITHDRAW ----------------
        elif action == 'withdraw':

            cursor.execute(
                "SELECT balance FROM users WHERE id=%s",
                (user_id,)
            )

            balance = cursor.fetchone()[0]

            if balance < amount:
                return "❌ Insufficient Balance"

            cursor.execute(
                "UPDATE users SET balance=balance-%s WHERE id=%s",
                (amount, user_id)
            )

            cursor.execute("""
            INSERT INTO transactions
            (user_id,type,amount,sender,receiver)
            VALUES(%s,%s,%s,%s,%s)
            """,
            (
                user_id,
                'Withdraw',
                amount,
                session['username'],
                session['username']
            ))

            db.commit()

    # CURRENT BALANCE
    cursor.execute(
        "SELECT balance, account_number FROM users WHERE id=%s",
        (user_id,)
    )

    data = cursor.fetchone()

    balance = data[0]
    account_number = data[1]

    return render_template(
        'dashboard.html',
        username=session['username'],
        balance=balance,
        role=session['role'],
        account_number=account_number
    )


# ---------------- MONEY TRANSFER ----------------
@app.route('/transfer', methods=['POST'])
def transfer():

    if 'user_id' not in session:
        return redirect('/login')

    sender_id = session['user_id']

    receiver_account = request.form['receiver_account']
    amount = float(request.form['amount'])

    # CHECK SENDER BALANCE
    cursor.execute(
        "SELECT balance FROM users WHERE id=%s",
        (sender_id,)
    )

    sender_balance = cursor.fetchone()[0]

    if sender_balance < amount:
        return "❌ Insufficient Balance"

    # FIND RECEIVER
    cursor.execute(
        "SELECT id,username FROM users WHERE account_number=%s",
        (receiver_account,)
    )

    receiver = cursor.fetchone()

    if not receiver:
        return "❌ Receiver Account Not Found"

    receiver_id = receiver[0]
    receiver_name = receiver[1]

    # DEDUCT SENDER
    cursor.execute(
        "UPDATE users SET balance=balance-%s WHERE id=%s",
        (amount, sender_id)
    )

    # ADD RECEIVER
    cursor.execute(
        "UPDATE users SET balance=balance+%s WHERE id=%s",
        (amount, receiver_id)
    )

    # SAVE TRANSACTION
    cursor.execute("""
    INSERT INTO transactions
    (user_id,type,amount,sender,receiver)
    VALUES(%s,%s,%s,%s,%s)
    """,
    (
        sender_id,
        'Transfer',
        amount,
        session['username'],
        receiver_name
    ))

    db.commit()

    return redirect('/dashboard')


# ---------------- TRANSACTION HISTORY ----------------
@app.route('/transactions')
def transactions():

    if 'user_id' not in session:
        return redirect('/login')

    cursor.execute("""
    SELECT id,type,amount,sender,receiver,time
    FROM transactions
    WHERE user_id=%s
    ORDER BY time DESC
    """,
    (session['user_id'],))

    data = cursor.fetchall()

    return render_template('transactions.html', data=data)


# ---------------- ADMIN DASHBOARD ----------------
@app.route('/admin')
def admin():

    if 'role' not in session or session['role'] != 'admin':
        return "❌ Access Denied"

    search = request.args.get('search')

    if search:

        cursor.execute("""
        SELECT id,username,balance,role,status,last_login,account_number
        FROM users
        WHERE username LIKE %s
        """,
        ('%' + search + '%',))

    else:

        cursor.execute("""
        SELECT id,username,balance,role,status,last_login,account_number
        FROM users
        """)

    users = cursor.fetchall()

    # ALL TRANSACTIONS
    cursor.execute("""
    SELECT id,user_id,type,amount,sender,receiver,time
    FROM transactions
    ORDER BY time DESC
    """)

    transactions = cursor.fetchall()

    # LOGIN LOGS
    cursor.execute("""
    SELECT id,user_id,username,login_time
    FROM login_logs
    ORDER BY login_time DESC
    """)

    logs = cursor.fetchall()
#-----------------------------------------------
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM transactions")
    total_transactions = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(balance),0) FROM users")
    total_balance = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE status='blocked'")
    blocked_accounts = cursor.fetchone()[0]
#-----------------------------------------------------------
    return render_template(
    'admin.html',
    users=users,
    transactions=transactions,
    logs=logs,
    total_users=total_users,
    total_transactions=total_transactions,
    total_balance=total_balance,
    blocked_accounts=blocked_accounts
)
# ---------------- BLOCK ACCOUNT ----------------
@app.route('/block/<int:user_id>')
def block_user(user_id):

    cursor.execute(
        "UPDATE users SET status='blocked' WHERE id=%s",
        (user_id,)
    )

    db.commit()

    return redirect('/admin')


# ---------------- UNBLOCK ACCOUNT ----------------
@app.route('/unblock/<int:user_id>')
def unblock_user(user_id):

    cursor.execute(
        "UPDATE users SET status='active' WHERE id=%s",
        (user_id,)
    )

    db.commit()

    return redirect('/admin')


# ---------------- DELETE ACCOUNT ----------------
@app.route('/delete/<int:user_id>')
def delete_user(user_id):

    # DELETE USER TRANSACTIONS
    cursor.execute(
        "DELETE FROM transactions WHERE user_id=%s",
        (user_id,)
    )

    # DELETE LOGIN LOGS
    cursor.execute(
        "DELETE FROM login_logs WHERE user_id=%s",
        (user_id,)
    )

    # DELETE USER
    cursor.execute(
        "DELETE FROM users WHERE id=%s",
        (user_id,)
    )

    db.commit()

    return redirect('/admin')


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():

    session.clear()

    return redirect('/')


# ---------------- RUN APP ----------------
if __name__ == "__main__":
    app.run(debug=True)