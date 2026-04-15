import os
import math
import requests
import openai
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ.get("DATAGOV_API_KEY")  # set this in Replit secrets
openai.api_key = os.environ.get("OPENAI_API_KEY")

if not API_KEY:
    raise RuntimeError("DATAGOV_API_KEY environment variable not set.")

app = Flask(__name__, static_folder="static", template_folder="templates")

SCORECARD_BASE = "https://api.data.gov/ed/collegescorecard/v1/schools"

FIELDS = [
    "id",
    "school.name",
    "school.city",
    "school.state",
    "latest.admissions.admission_rate.overall",
    "latest.student.size",
    "latest.cost.avg_net_price.overall",
    "latest.aid.pell_grant_rate",
    "latest.admissions.sat_scores.average.overall",
    "latest.admissions.act_scores.midpoint.cumulative"
]

def call_scorecard(params):
    params = params.copy()
    params["api_key"] = API_KEY
    params["fields"] = ",".join(FIELDS)
    params["per_page"] = 100
    r = requests.get(SCORECARD_BASE, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def safe_get(item, path, default=None):
    # First try the full path as a single key (API returns flat keys like 'latest.student.size')
    if path in item:
        return item[path]
    # Otherwise try nested navigation
    cur = item
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def locale_to_type(locale_code):
    try:
        n = int(locale_code)
    except:
        return "Unknown"
    if 11 <= n <= 32:
        if 11 <= n <= 13: return "urban"
        if 21 <= n <= 23: return "suburban"
        if 31 <= n <= 33: return "rural"
    return "other"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/recommend", methods=["POST"])
def recommend():
    print("POST /recommend received")
    data = request.json or {}
    print("Payload:", data)

    user = {
        "gpa": data.get("gpa"),
        "sat": data.get("sat"),
        "act": data.get("act"),
        "sai": data.get("sai"),
        "financial": data.get("financial"),
        "intended_major": data.get("intended_major"),
        "location_type": data.get("location_type") or "no_pref",
        "population": data.get("population"),
        "control": data.get("control") or "either",
        "hbcu_pref": data.get("hbcu_pref") or None
    }

    # Convert ACT to SAT if needed
    if user["act"] and not user["sat"]:
        try:
            act = float(user["act"])
            user["act_est_sat"] = 400 + (act / 36.0) * 1200
        except:
            user["act_est_sat"] = None

    params = {}
    if data.get("state"):
        params["school.state"] = data["state"]
    
    # Filter by 2-year vs 4-year schools
    if data.get("two_or_four") == "2":
        params["school.degrees_awarded.predominant"] = "2"
    elif data.get("two_or_four") == "4":
        params["school.degrees_awarded.predominant"] = "3"
    
    # Filter schools currently operating
    params["school.operating"] = "1"
    
    # Add SAT range filter if user provided SAT score
    if user.get("sat"):
        try:
            sat_score = int(user["sat"])
            # Look for schools within a reasonable range
            params["latest.admissions.sat_scores.average.overall__range"] = f"{sat_score-300}..{sat_score+300}"
        except:
            pass

    try:
        resp = call_scorecard(params)
    except Exception as e:
        return jsonify({"error": f"Error calling College Scorecard API: {str(e)}"}), 500

    results = resp.get("results", [])
    print(f"Got {len(results)} results from API")
    if results:
        print("Sample school data:", results[0])
    scored = []

    # Score each school based on user preferences
    for s in results:
        score = 0
        
        # Filter by population if specified
        sch_size = safe_get(s, "latest.student.size")
        if user["population"] and sch_size:
            try:
                n = int(sch_size)
                if user["population"] == "small" and n >= 5000:
                    continue
                if user["population"] == "medium" and (n < 5000 or n >= 15000):
                    continue
                if user["population"] == "large" and n < 15000:
                    continue
                score += 5  # Bonus for matching size preference
            except:
                pass
        
        # SAT proximity scoring
        user_sat = user.get("sat") or user.get("act_est_sat")
        school_sat = safe_get(s, "latest.admissions.sat_scores.average.overall")
        if user_sat and school_sat:
            try:
                user_sat = float(user_sat)
                school_sat = float(school_sat)
                sat_diff = abs(user_sat - school_sat)
                # Closer scores = better match (within 200 points is good)
                score += max(0, 10 - (sat_diff / 50))
            except:
                pass
        
        # Admission rate vs GPA match
        adm_rate = safe_get(s, "latest.admissions.admission_rate.overall")
        if adm_rate and user.get("gpa"):
            try:
                adm = float(adm_rate)
                gpa = float(user["gpa"])
                # High GPA students can aim for selective schools
                if gpa >= 3.7 and adm < 0.3:
                    score += 8
                elif gpa >= 3.3 and 0.3 <= adm < 0.6:
                    score += 8
                elif gpa >= 2.5 and adm >= 0.6:
                    score += 8
                else:
                    score += 3  # Some match
            except:
                pass
        
        # Affordability matching
        net_price = safe_get(s, "latest.cost.avg_net_price.overall")
        if net_price and user.get("sai") is not None:
            try:
                net = float(net_price)
                sai = float(user["sai"])
                # If SAI can cover net price, that's great
                if sai >= net:
                    score += 10
                elif sai >= net * 0.5:
                    score += 5
            except:
                pass
        
        scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Debug: Print top scores
    print(f"Top 5 schools by score:")
    for i, (score, sch) in enumerate(scored[:5]):
        print(f"  {i+1}. {safe_get(sch, 'school.name')} - Score: {score:.2f}")
    
    top = [s for sc, s in scored[:5]]

    out = []
    for s in top:
        pell_rate = safe_get(s, "latest.aid.pell_grant_rate")
        sch = {
            "id": safe_get(s, "id"),
            "name": safe_get(s, "school.name"),
            "city": safe_get(s, "school.city"),
            "state": safe_get(s, "school.state"),
            "admission_rate": safe_get(s, "latest.admissions.admission_rate.overall"),
            "avg_sat": safe_get(s, "latest.admissions.sat_scores.average.overall"),
            "avg_act": safe_get(s, "latest.admissions.act_scores.midpoint.cumulative"),
            "student_size": safe_get(s, "latest.student.size"),
            "avg_net_price": safe_get(s, "latest.cost.avg_net_price.overall"),
            "pell_grant_rate": pell_rate
        }
        out.append(sch)

    return jsonify({
        "query_count": len(results),
        "recommendations": out
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
