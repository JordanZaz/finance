import os
import sqlalchemy
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
import datetime
from helpers import apology, login_required, lookup, usd

app = Flask(__name__)

app.config["TEMPLATES_AUTO_RELOAD"] = True

app.jinja_env.filters["usd"] = usd

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

uri = os.getenv("DATABASE_URL")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://")
db = SQL(uri)

if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    user_id = session["user_id"]

    transactions_db = db.execute("SELECT symbol, SUM(shares) AS shares, transactions.price FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0", user_id)
    cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash1 = cash_db[0]["cash"]
    cash = usd(cash1)


    return render_template("index.html", database = transactions_db, cash=cash)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    if request.method == "GET":
         return render_template("buy.html")

    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("must provide a symbol")

        stock = lookup(symbol.upper())

        if stock == None:
            return apology("symbol does not exist")

        transaction_value = float(shares) * stock["price"]

        user_id = session["user_id"]
        user_cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        user_cash = user_cash_db[0]["cash"]

        if user_cash < transaction_value:
            return apology("Not enough money")

        uptd_cash = user_cash - transaction_value

        db.execute("UPDATE users SET cash = ? WHERE id = ?", uptd_cash, user_id)

        date = datetime.datetime.now()

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, date) VALUES (?, ?, ?, ?, ?)", user_id, stock["symbol"], shares, stock["price"], date)

        flash("Bought!")


        return redirect("/")


@app.route("/history")
@login_required
def history():

    user_id = session["user_id"]
    transactions_db = db.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC", user_id)

    return render_template("history.html", transactions = transactions_db)



@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():

    user_id = session["user_id"]

    if request.method == "GET":

        cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash1 = cash_db[0]["cash"]
        cash = usd(cash1)
        return render_template("deposit.html", cash=cash)

    else:

        deposit = request.form.get("deposit")

        if not deposit:
            return apology("Must Provide number of cash deposits")

        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", deposit, user_id)

        return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    session.clear()

    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 403)

        elif not request.form.get("password"):
            return apology("must provide password", 403)

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    session.clear()

    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    if request.method == "GET":
        return render_template("quote.html")

    else:
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("Must Provide Symbol")

        stock = lookup(symbol.upper())

        if stock == None:
            return apology("Stock Does Not Exist")

        return render_template("quoted.html", name = stock["name"], price = usd(stock["price"]), symbol = stock["symbol"])

    return apology("TODO")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "GET":
        return render_template("register.html")

    else:
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("Must Give Username")
        if not password:
            return apology("Must Give Password")
        if not confirmation:
            return apology("Must Give Confirmation")
        if password != confirmation:
            return apology("Password Did Not Match")

        hash = generate_password_hash(password)

        try:
            new_user = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)
        except:
            return apology("Username Already Exists")

        session["user_id"] = new_user

        return redirect("/")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "GET":
        user_id = session["user_id"]
        symbols_user = db.execute("SELECT DISTINCT(symbol) FROM transactions WHERE user_id = ?", user_id)

        return render_template("sell.html", symbols = [row["symbol"] for row in symbols_user])

    else:
        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))

        if not symbol:
            return apology("must provide a symbol")

        stock = lookup(symbol.upper())

        if stock == None:
            return apology("symbol does not exist")

        transaction_value = float(shares) * stock["price"]

        user_id = session["user_id"]
        user_cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        user_cash = user_cash_db[0]["cash"]

        user_shares = db.execute("SELECT SUM(shares) AS shares FROM transactions WHERE user_id = ? AND symbol = ?", user_id, symbol)

        user_shares_real = user_shares[0]["shares"]

        if shares > user_shares_real:
            return apology("Selected too many shares")

        uptd_cash = user_cash + transaction_value

        db.execute("UPDATE users SET cash = ? WHERE id = ?", uptd_cash, user_id)

        date = datetime.datetime.now()

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, date) VALUES (?, ?, ?, ?, ?)", user_id,  stock["symbol"], (-1) * shares, stock["price"], date)

        flash("Sold!")


        return redirect("/")

