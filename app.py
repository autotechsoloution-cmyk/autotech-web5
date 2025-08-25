from flask import Flask, render_template, request, redirect, url_for, session, g
import os, json, math, requests

app = Flask(__name__)
app.secret_key = "change-me"

# ---- Demo data (swap for your big JSON later) ----
UNITS = [
    {"id": 0, "Brand": "Toyota", "Model (Series/Gen)": "Corolla (E170)", "Years From": 2013, "Years To": 2018, "Head Unit Size": '9"', "Luxury": "No", "PriceAUD": 550},
    {"id": 1, "Brand": "BMW",    "Model (Series/Gen)": "3 Series (E90)",   "Years From": 2005, "Years To": 2012, "Head Unit Size": '7"', "Luxury": "Yes","PriceAUD": 620},
]

# Attach an image placeholder for each item (static/units/{id}.jpg if you later add real photos)
for u in UNITS:
    img_candidate = os.path.join("static", "units", f"{u['id']}.jpg")
    u["img"] = f"units/{u['id']}.jpg" if os.path.exists(img_candidate) else "placeholder.jpg"

# Currency + local install areas
CURRENCIES = {"AUD":1.0,"USD":0.66,"EUR":0.61,"NZD":1.08,"GBP":0.52}
SERVICE_AREAS = [{"name":"Brisbane","start":4000,"end":4209},{"name":"Gold Coast","start":4207,"end":4228}]
CALLOUT_FEE = 60

def is_local(pc):
    try:
        n = int(str(pc).strip())
    except:
        return False
    return any(a["start"] <= n <= a["end"] for a in SERVICE_AREAS)

def install_fee(u):  # per your rule
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

# ---- Premium audio hints for VIN ----
PREMIUM = {
    "toyota":["jbl"],
    "bmw":["harman kardon","bowers & wilkins","b&w"],
    "mercedes-benz":["burmester","bang & olufsen","harman kardon"],
    "audi":["bang & olufsen","bose","sonos"],
    "mitsubishi":["rockford","rockford fosgate"],
    "land rover":["meridian"],
    "lexus":["mark levinson"]
}

def decode_vin(vin):
    """Return dict: {Year, Make, Model, premium_hint}"""
    r = requests.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json", timeout=12)
    r.raise_for_status()
    j = r.json()
    d = {row.get("Variable"):row.get("Value") for row in j.get("Results",[])}
    out = {"Year": d.get("Model Year") or d.get("ModelYear"),
           "Make": d.get("Make"), "Model": d.get("Model")}
    mk = (out.get("Make") or "").lower()
    text = " ".join((d.get("Trim") or "", d.get("Series") or "", d.get("Model") or "")).lower()
    premium_hint = None
    for brand, keys in PREMIUM.items():
        if brand in mk:
            for k in keys:
                if k in text:
                    premium_hint = k.title()
    out["premium_hint"] = premium_hint
    return out

# ---- Routes ----

@app.route("/", methods=["GET","POST"])
def home():
    # currency picker
    if request.method == "POST" and request.form.get("ccy"):
        session["ccy"] = (request.form.get("ccy") or "AUD").upper()
        return redirect(url_for("home"))

    # inline VIN checker on homepage
    vin_result = None
    vin_error = None
    if request.method == "POST" and request.form.get("vin"):
        vin = request.form.get("vin","").strip()
        try:
            vin_result = decode_vin(vin)
        except Exception as e:
            vin_error = f"VIN lookup failed: {e}"

    most, fav = UNITS, list(reversed(UNITS))
    return render_template("index.html", most=most, fav=fav, vin_result=vin_result, vin_error=vin_error)

@app.get("/shop")
def shop():
    return render_template("shop.html", items=UNITS)

@app.route("/unit/<int:uid>", methods=["GET","POST"])
def unit_detail(uid):
    u = next((x for x in UNITS if x["id"]==uid), None)
    if not u: return redirect(url_for("shop"))

    # Defaults for the form
    pc = session.get("postcode","")
    local = is_local(pc)

    if request.method == "POST":
        # Options from the detail page
        custom_sound = request.form.get("custom_sound") == "yes"
        premium_brand = request.form.get("premium_brand") or ""
        extra_mic = request.form.get("extra_mic") == "on"
        keep_sw_controls = request.form.get("keep_sw_controls") == "on"
        want_install = request.form.get("want_install") == "on"
        want_callout = request.form.get("want_callout") == "on"
        postcode = (request.form.get("postcode") or "").strip()
        session["postcode"] = postcode  # remember for cart
        local = is_local(postcode)

        # Add to cart with selected options
        cart = session.get("cart_detail", [])
        cart.append({
            "uid": uid,
            "options": {
                "custom_sound": custom_sound,
                "premium_brand": premium_brand,
                "extra_mic": extra_mic,
                "keep_sw_controls": keep_sw_controls,
                "want_install": want_install if local else False,
                "want_callout": want_callout if local else False,
                "postcode": postcode
            }
        })
        session["cart_detail"] = cart
        return redirect(url_for("cart"))

    return render_template("unit_detail.html", u=u, local_ok=local, postcode=pc)

@app.post("/add/<int:uid>")
def add_quick(uid):
    """Fallback quick add (no options)"""
    if not next((x for x in UNITS if x["id"]==uid), None): return redirect(url_for("shop"))
    cart = session.get("cart_detail", [])
    cart.append({"uid": uid, "options": {}})
    session["cart_detail"] = cart
    return redirect(url_for("cart"))

@app.post("/remove/<int:i>")
def remove(i):
    cart = session.get("cart_detail", [])
    if 0 <= i < len(cart): del cart[i]
    session["cart_detail"] = cart
    return redirect(url_for("cart"))

@app.route("/cart", methods=["GET","POST"])
def cart():
    # merge options-aware cart
    cart = session.get("cart_detail", [])
    # Update postcode / toggles at cart level if user edits here
    if request.method == "POST":
        postcode = (request.form.get("postcode") or "").strip()
        want_install = request.form.get("want_install") == "on"
        want_callout = request.form.get("want_callout") == "on"
        session["postcode"] = postcode
        # apply to each item options (respect local gating)
        local = is_local(postcode)
        for it in cart:
            it.setdefault("options", {})
            it["options"]["postcode"] = postcode
            it["options"]["want_install"] = want_install if local else False
            it["options"]["want_callout"] = want_callout if local else False
        session["cart_detail"] = cart

    # compute totals
    items = []
    for it in cart:
        u = next((x for x in UNITS if x["id"]==it["uid"]), None)
        if not u: continue
        items.append({"unit": u, "opt": it.get("options", {})})

    pc = session.get("postcode","")
    local = is_local(pc)
    sub = sum(x["unit"]["PriceAUD"] for x in items)
    inst = sum(install_fee(x["unit"]) for x in items if x["opt"].get("want_install") and local)
    call = CALLOUT_FEE if (items and any(x["opt"].get("want_callout") for x in items) and local) else 0
    ship = ship_est(pc, len(items)) if pc else 0
    grand = sub + inst + call + ship

    return render_template("cart.html",
        items=items, postcode=pc, local_ok=local,
        sub_units=sub, install_total=inst, callout_total=call, shipping=ship, grand=grand, fx=fx)

@app.get("/checkout")
def checkout():
    cart = session.get("cart_detail", [])
    items = []
    for it in cart:
        u = next((x for x in UNITS if x["id"]==it["uid"]), None)
        if not u: continue
        items.append({"unit": u, "opt": it.get("options", {})})

    if not items: return redirect(url_for("shop"))
    pc = session.get("postcode","")
    local = is_local(pc)
    sub = sum(x["unit"]["PriceAUD"] for x in items)
    inst = sum(install_fee(x["unit"]) for x in items if x["opt"].get("want_install") and local)
    call = CALLOUT_FEE if (items and any(x["opt"].get("want_callout") for x in items) and local) else 0
    ship = ship_est(pc, len(items)) if pc else 0
    grand = sub + inst + call + ship
    return render_template("checkout.html", items=items, sub_units=sub, install_total=inst, callout_total=call, shipping=ship, grand=grand, fx=fx)

if __name__ == "__main__":
    app.run(debug=True)
