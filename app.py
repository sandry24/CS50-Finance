from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


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
    """Show portfolio of stocks"""
    stocks = db.execute(
        "SELECT symbol, SUM(shares) AS shares FROM transactions "
        "WHERE user_id=? GROUP BY symbol HAVING SUM(shares) != 0",
        session["user_id"]
    )

    cash = db.execute(
        "SELECT cash FROM users WHERE id=?",
        session["user_id"]
    )[0]["cash"]

    total = cash

    for stock in stocks:
        stock_price = lookup(stock["symbol"])["price"]
        stock["current_price"] = stock_price
        stock["total_price"] = stock_price * stock["shares"]
        total += stock["total_price"]

        # Formatting
        stock["current_price"] = usd(stock["current_price"])
        stock["total_price"] = usd(stock["total_price"])

    cash = usd(cash)
    total = usd(total)

    return render_template("index.html", stocks=stocks, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("must provide symbol", 400)

        elif not shares:
            return apology("must provide shares", 400)

        elif not is_valid_integer(shares):
            return apology("invalid shares", 400)

        shares = int(shares)
        stock = lookup(symbol)
        cash = db.execute(
            "SELECT cash FROM users WHERE id=?",
            session["user_id"]
        )[0]["cash"]

        if shares < 1:
            return apology("invalid shares", 400)

        elif not stock:
            return apology("invalid symbol", 400)

        elif cash < stock["price"] * shares:
            return apology("insufficient balance", 400)

        cash -= stock["price"] * shares
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
            session["user_id"],
            stock["symbol"],
            shares,
            stock["price"]
        )

        db.execute(
            "UPDATE users SET cash=? WHERE id=?",
            cash,
            session["user_id"]
        )

        return redirect("/")
    else:
        # Special case if clicked from index
        symbol = request.args.get("symbol", "")
        return render_template("buy.html", symbol=symbol)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute(
        "SELECT * FROM transactions WHERE user_id=? ORDER BY transacted_at DESC",
        session["user_id"]
    )

    for transaction in transactions:
        transaction["price"] = usd(transaction["price"])
    return render_template("history.html", transactions=transactions)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Add funds to user balance"""
    if request.method == "POST":
        amount = request.form.get("amount")

        if not amount:
            return apology("must provide amount", 400)

        if not is_valid_float(amount):
            return apology("invalid amount", 400)

        amount = float(amount)
        amount = round(amount, 2)
        cash = db.execute(
            "SELECT cash FROM users WHERE id=?",
            session["user_id"]
        )[0]["cash"]

        cash += amount
        db.execute(
            "UPDATE users SET cash=? WHERE id=?",
            cash,
            session["user_id"]
        )

        flash(f"Successfully added {usd(amount)} to user balance.")

        return redirect("/")
    else:
        return render_template("add.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?",
            request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        if not stock:
            return apology("invalid symbol", 400)

        return render_template("quoted.html", symbol=stock["symbol"], price=usd(stock["price"]))
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)

        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Ensure this username does not exist
        try:
            db.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?)",
                request.form.get("username"),
                generate_password_hash(request.form.get("password"))
            )

            rows = db.execute(
                "SELECT * FROM users WHERE username = ?", request.form.get("username")
            )

            session["user_id"] = rows[0]["id"]
            flash(f"Successfully registered!")
        except ValueError:
            return apology("username already exists", 400)

        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("must provide symbol", 400)

        elif not shares:
            return apology("must provide shares", 400)

        elif not is_valid_integer(shares):
            return apology("invalid shares", 400)

        shares = int(shares)
        stock = lookup(symbol)
        cash = db.execute(
            "SELECT cash FROM users WHERE id=?",
            session["user_id"]
        )[0]["cash"]

        if shares < 1:
            return apology("invalid shares", 400)

        elif not stock:
            return apology("invalid symbol", 400)

        shares_query = db.execute(
            "SELECT SUM(shares) AS shares FROM transactions WHERE user_id=? AND symbol=? GROUP BY symbol",
            session["user_id"],
            stock["symbol"]
        )

        owned_shares = shares_query[0]["shares"]
        profit = stock["price"] * shares

        if shares > owned_shares:
            return apology("insufficient balance", 400)

        cash += profit
        owned_shares -= shares

        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
            session["user_id"],
            stock["symbol"],
            -shares,
            stock["price"]
        )

        db.execute(
            "UPDATE users SET cash=? WHERE id=?",
            cash,
            session["user_id"]
        )

        flash(f"Successfully sold {shares} shares of {stock['symbol']} for {usd(profit)}.")

        return redirect("/")
    else:
        symbols_query = db.execute(
            "SELECT symbol FROM transactions WHERE user_id=? GROUP BY symbol",
            session["user_id"]
        )

        owned_symbols = [row["symbol"] for row in symbols_query]

        # Special case if clicked from index
        symbol = request.args.get("symbol", "")
        return render_template("sell.html", owned_symbols=owned_symbols, symbol=symbol)


def is_valid_integer(value):
    try:
        return int(value) and int(value) == float(value)
    except (ValueError, TypeError):
        return False


def is_valid_float(value):
    try:
        float(value)
    except (ValueError, TypeError):
        return False
    return True
