from flask import Flask, render_template, request, redirect, url_for, session, g
import os, requests

app = Flask(__name__)
app.secret_key = "change-me"

# ---- Demo data (swap for your big JSON later) ----
UNITS = [
    {"id": 0, "Brand": "Toyota", "Model (Series/Gen)": "Corolla (E170)", "Years From": 2013, "Years To": 2018, "Head Unit Size": '9"', "Luxury": "No", "PriceAUD": 550},
    {"id": 1, "Brand": "BMW",    "Model (Series/Gen)": "3 Series (E90)",   "Years From": 2005, "Years To": 2012, "Head Unit Size": '7"', "Luxury": "Yes","PriceAUD": 620},
]

# preload placeholder images
for u in UNITS:
    img_candidate = os.path.join("static", "units", f"{u['id']}.jpg")
    u["img"] = f"units/{u['id']}.jpg" if os.path.exists(img_candidate) else "placeholder.jpg"

# Currency + local install areas
CURRENCIES = {"AUD":1.0,"USD":0.66,"EUR":0.61,"NZD":1.08,"GBP":0.52}
SERVICE_AREAS = [{"name":"Brisbane","start":4000,"end":4209},{"name":"Gold Coast","start":4207,"end":4228}]
CALLOUT_FEE = 60
GPS_PRICE = 50
DASHCAM_PRICE = 80

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
    if 4207<=n<=4228: return "GC"
    if 4000<=n<=4999: return "QLD"
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
    if request.method == "POST" and request.form.get("ccy"):
        session["ccy"] = (request.form.get("ccy") or "AUD").upper()
        return redirect(url_for("home"))

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

@app.get("/lookup")
def lookup():
    simple = []
    for u in UNITS:
        simple.append({
            "id": u["id"], "brand": u["Brand"], "model": u["Model (Series/Gen)"],
            "y0": u["Years From"], "y1": u["Years To"], "size": u["Head Unit Size"],
            "lux": u["Luxury"], "price": u["PriceAUD"], "img": u.get("img","placeholder.jpg")
        })
    return render_template("lookup.html", items=simple)

@app.route("/unit/<int:uid>", methods=["GET","POST"])
def unit_detail(uid):
    u = next((x for x in UNITS if x["id"]==uid), None)
    if not u: return redirect(url_for("shop"))

    pc = session.get("postcode","")
    local = is_local(pc)

    if request.method == "POST":
        # Sequence: audio -> onsite -> extras
        custom_sound = request.form.get("custom_sound") == "yes"
        premium_brand = request.form.get("premium_brand") or ""
        postcode = (request.form.get("postcode") or "").strip()
        onsite = request.form.get("onsite") == "on"  # Install + Callout in one
        gps = request.form.get("gps") == "on"
        dashcam = request.form.get("dashcam") == "on"

        session["postcode"] = postcode
        local = is_local(postcode)

        want_install = onsite and local
        want_callout = onsite and local

        cart = session.get("cart_detail", [])
        cart.append({
            "uid": uid,
            "options": {
                "custom_sound": custom_sound,
                "premium_brand": premium_brand,
                "postcode": postcode,
                "want_install": want_install,
                "want_callout": want_callout,
                "gps": gps,
                "dashcam": dashcam
            }
        })
        session["cart_detail"] = cart
        return redirect(url_for("cart"))

    return render_template("unit_detail.html", u=u, local_ok=local, postcode=pc,
                           gps_price=GPS_PRICE, dash_price=DASHCAM_PRICE)

@app.post("/add/<int:uid>")
def add_quick(uid):
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
    cart = session.get("cart_detail", [])

    if request.method == "POST":
        postcode = (request.form.get("postcode") or "").strip()
        # These apply across items if user ticks them here:
        apply_install = request.form.get("want_install") == "on"
        apply_callout = request.form.get("want_callout") == "on"
        session["postcode"] = postcode
        local = is_local(postcode)
        for it in cart:
            it.setdefault("options", {})
            it["options"]["postcode"] = postcode
            # keep earlier per-item choices but allow cart-level override
            it["options"]["want_install"] = apply_install and local
            it["options"]["want_callout"] = apply_callout and local
        session["cart_detail"] = cart

    items = []
    for it in cart:
        u = next((x for x in UNITS if x["id"]==it["uid"]), None)
        if not u: continue
        items.append({"unit": u, "opt": it.get("options", {})})

    pc = session.get("postcode","")
    local = is_local(pc)

    sub_units = sum(x["unit"]["PriceAUD"] for x in items)
    extras_total = 0
    for x in items:
        if x["opt"].get("gps"): extras_total += GPS_PRICE
        if x["opt"].get("dashcam"): extras_total += DASHCAM_PRICE

    inst_total = sum(install_fee(x["unit"]) for x in items if x["opt"].get("want_install") and local)
    callout_total = CALLOUT_FEE if (items and any(x["opt"].get("want_callout") for x in items) and local) else 0
    shipping = ship_est(pc, len(items)) if pc else 0
    grand = sub_units + extras_total + inst_total + callout_total + shipping

    return render_template("cart.html",
        items=items, postcode=pc, local_ok=local,
        sub_units=sub_units, extras_total=extras_total,
        install_total=inst_total, callout_total=callout_total,
        shipping=shipping, grand=grand, fx=fx)

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

    sub_units = sum(x["unit"]["PriceAUD"] for x in items)
    extras_total = 0
    for x in items:
        if x["opt"].get("gps"): extras_total += GPS_PRICE
        if x["opt"].get("dashcam"): extras_total += DASHCAM_PRICE

    inst_total = sum(install_fee(x["unit"]) for x in items if x["opt"].get("want_install") and local)
    callout_total = CALLOUT_FEE if (items and any(x["opt"].get("want_callout") for x in items) and local) else 0
    shipping = ship_est(pc, len(items)) if pc else 0
    grand = sub_units + extras_total + inst_total + callout_total + shipping

    return render_template("checkout.html",
        items=items, sub_units=sub_units, extras_total=extras_total,
        install_total=inst_total, callout_total=callout_total,
        shipping=shipping, grand=grand, fx=fx)

if __name__ == "__main__":
    app.run(debug=True)
