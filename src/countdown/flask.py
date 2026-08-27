from flask import Flask, render_template_string, request, redirect
from countdown.config_manager import config_manager

app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html>
<head><title>Transit Display Settings</title></head>
<body style="font-family: sans-serif; padding: 20px;">
    <h2>Transit Display Configuration</h2>
    <form method="POST">
        <label>Postcode:</label><br>
        <input type="text" name="postcode" value="{{ config.postcode }}" style="padding: 5px; margin-bottom: 10px;"><br>

        <label>Preferred Stop IDs (comma-separated):</label><br>
        <input type="text" name="stop_ids" value="{{ config.stop_ids | join(', ') }}" style="padding: 5px; width: 300px; margin-bottom: 10px;"><br>

        <button type="submit" style="padding: 8px 15px;">Save Settings</button>
    </form>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def settings():
    config = config_manager.load_config()
    if request.method == "POST":
        config["postcode"] = request.form.get("postcode", "").strip()
        # Parse comma-separated stop IDs into a clean list
        raw_stops = request.form.get("stop_ids", "")
        config["stop_ids"] = [s.strip() for s in raw_stops.split(",") if s.strip()]
        config_manager.save_config(config)
        return redirect("/")

    return render_template_string(HTML_TEMPLATE, config=config)