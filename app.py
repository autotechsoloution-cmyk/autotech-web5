from flask import Flask, render_template
app = Flask(__name__)

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/shop")
def shop():
    items = [
        {"id": 0, "brand": "Toyota", "model": "Corolla (E170)", "price": 550},
        {"id": 1, "brand": "BMW", "model": "3 Series (E90)", "price": 620},
    ]
    return render_template("shop.html", items=items)

@app.get("/unit/<int:uid>")
def unit_detail(uid):
    demo = [
        {"id": 0, "brand": "Toyota", "model": "Corolla (E170)", "price": 550, "years": "2013–2018", "size": '9"'},
        {"id": 1, "brand": "BMW", "model": "3 Series (E90)", "price": 620, "years": "2005–2012", "size": '7"'},
    ]
    u = next((x for x in demo if x["id"] == uid), None)
    if not u:
        return "Not found", 404
    return render_template("unit_detail.html", u=u)

if __name__ == "__main__":
    app.run(debug=True)

