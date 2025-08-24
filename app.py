from flask import Flask, render_template, request, redirect, url_for, session, g
import json, math, requests

app = Flask(__name__)
app.secret_key = "change-me"

# ---- Data (you’ll replace with your big JSON later) ----
UNITS = [
    {"id": 0, "Brand": "Toyota", "Model (Series/Gen)": "Corolla (E170)", "Years From": 2013, "Years To": 2018, "Head Unit Size": '9"', "Luxury": "No", "PriceAUD": 550},
    {"id": 1, "Brand": "BMW",    "Model (Series/Gen)": "3 Series (E90)",   "Years From": 2005, "Years To": 2012, "Head Unit Size": '7"', "Luxury": "Yes","PriceAUD": 620},
]

CURRENCIES = {"AUD":1.0,"USD":0.66,"EUR":0.61,"NZD":1.08,"GBP":0.52}
SERVICE_AREAS = [{"name":"Brisbane","start":4000,"end":4209},{"name":"Gold Coast","start":4207,"end":4228}]
CALLOUT_FEE = 60

def is_local(pc):
    try:
        n = int(str(pc).strip())
    except:
        return False
    return any(a["start"] <= n <= a["end"] for a in SERVICE_AREAS)

def install_fee(u):
    return 130 if str(u.get("Luxury","")).lower()=="yes" else 90

def zone(pc):
    try: n = int(str(pc).strip())
    except: return "AUS"
    if 4000<=n<=4999: return "QLD"
    if 4207<=n<=4228: return "GC"
    return "AUS"

def ship_est(pc, count):
    base = {"QLD":12.95,"GC":12.95,"AUS":14.95}
    return base.get(zone(pc),14.95) + max(0, count-1)*3

@app.before_request
def _bef():
    g.ccy = session.get("ccy","AUD")

def fx(aud):
    return round(aud * CURRENCIES.get(g.ccy,1.0), 2)

@app.get("/")
def home():
    most, fav = UNITS, list(reversed(UNITS))
    return render_template("index.html", most=most, fav=fav)

@app.post("/set_currency")
def set_currency():
    session["ccy"] = (request.form.get("ccy") or "AUD").upper()
    return redirect(request.referrer or url_for("home"))

@app.get("/shop")
def shop():
    return render_template("shop.html", items=UNITS)

@app.get("/unit/<int:uid>")
def unit_detail(uid):
    u = next((x for x in UNITS if x["id"]==uid), None)
    if not u: return redirect(url_for("shop"))
    return render_template("unit_detail.html", u=u)

@app.post("/add/<int:uid>")
def add(uid):
    if not next((x for x in UNITS if x["id"]==uid), None):
        return redirect(url_for("shop"))
    cart = session.get("cart",[])
    cart.append(uid); session["cart"]=cart
    return redirect(url_for("cart"))

@app.post("/remove/<int:i>")
def remove(i):
    cart = session.get("cart",[])
    if 0 <= i < len(cart): del cart[i]
    session["cart"]=cart
    return redirect(url_for("cart"))

@app.route("/cart", methods=["GET","POST"])
def cart():
    pc = session.get("postcode","")
    want_install = session.get("want_install", False)
    want_callout = session.get("want_callout", False)
    if request.method=="POST":
        pc=(request.form.get("postcode") or "").strip()
        want_install = request.form.get("want_install")=="on"
        want_callout = request.form.get("want_callout")=="on"
        session.update({"postcode":pc,"want_install":want_install,"want_callout":want_callout})

    cart_ids = session.get("cart",[])
    items = [x for x in UNITS if x["id"] in cart_ids]
    local = is_local(pc)

    sub = sum(x["PriceAUD"] for x in items)
    inst = sum(install_fee(x) for x in items) if (local and want_install) else 0
    call = CALLOUT_FEE if (items and local and want_callout) else 0
    ship = ship_est(pc, len(items)) if pc else 0
    grand = sub + inst + call + ship

    return render_template("cart.html",
        items=items, postcode=pc, local_ok=local,
        want_install=want_install, want_callout=want_callout,
        sub_units=sub, install_total=inst, callout_total=call, shipping=ship, grand=grand, fx=fx)

@app.get("/checkout")
def checkout():
    cart_ids = session.get("cart",[])
    items = [x for x in UNITS if x["id"] in cart_ids]
    if not items: return redirect(url_for("shop"))
    pc = session.get("postcode","")
    local = is_local(pc)
    sub = sum(x["PriceAUD"] for x in items)
    inst = sum(install_fee(x) for x in items) if (local and session.get("want_install")) else 0
    call = CALLOUT_FEE if (items and local and session.get("want_callout")) else 0
    ship = ship_est(pc, len(items)) if pc else 0
    grand = sub + inst + call + ship
    return render_template("checkout.html", items=items, sub_units=sub, install_total=inst, callout_total=call, shipping=ship, grand=grand, fx=fx)

# ---- VIN checker (NHTSA VPIC) ----
PREMIUM = {
    "toyota":["jbl"], "bmw":["harman kardon","bowers & wilkins"], "mercedes-benz":["burmester","bang & olufsen","harman kardon"],
    "audi":["bang & olufsen","bose"], "mitsubishi":["rockford","rockford fosgate"], "land rover":["meridian"], "lexus":["mark levinson"]
}

@app.route("/vin", methods=["GET","POST"])
def vin():
    decoded = None; premium_hint=None; err=None
    if request.method=="POST":
        vin = (request.form.get("vin") or "").strip()
        try:
            r = requests.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json", timeout=10)
            r.raise_for_status(); j = r.json()
            d = {row.get("Variable"):row.get("Value") for row in j.get("Results",[])}
            decoded = {"Year": d.get("Model Year") or d.get("ModelYear"), "Make": d.get("Make"), "Model": d.get("Model")}
            mk = (decoded.get("Make") or "").lower()
            text = " ".join((d.get("Trim") or "", d.get("Series") or "", d.get("Model") or "")).lower()
            for brand, keys in PREMIUM.items():
                if brand in mk:
                    for k in keys:
                        if k in text: premium_hint = k.title()
        except Exception as e:
            err = f"VIN lookup failed: {e}"
    return render_template("vin.html", decoded=decoded, premium_hint=premium_hint, err=err)

if __name__ == "__main__":
    app.run(debug=True)
