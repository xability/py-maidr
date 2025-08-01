import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for Flask

from flask import Flask
import matplotlib.pyplot as plt
import seaborn as sns
import maidr
from maidr.util.environment import Environment
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def index():
    # Log environment detection
    logger.info("=== Environment Detection ===")
    logger.info(f"is_flask(): {Environment.is_flask()}")
    logger.info(f"is_notebook(): {Environment.is_notebook()}")
    logger.info(f"is_shiny(): {Environment.is_shiny()}")
    logger.info(f"get_renderer(): {Environment.get_renderer()}")

    # Check iframe detection logic
    use_iframe = True
    flask_detected = Environment.is_flask()
    notebook_detected = Environment.is_notebook()
    shiny_detected = Environment.is_shiny()

    logger.info("=== Iframe Detection Logic ===")
    logger.info(f"use_iframe: {use_iframe}")
    logger.info(f"flask_detected: {flask_detected}")
    logger.info(f"notebook_detected: {notebook_detected}")
    logger.info(f"shiny_detected: {shiny_detected}")
    logger.info("Condition: use_iframe and (flask_detected or notebook_detected or shiny_detected)")
    logger.info(f"Result: {use_iframe and (flask_detected or notebook_detected or shiny_detected)}")

    # Load the penguins dataset
    penguins = sns.load_dataset("penguins")

    # Create a bar plot showing the average body mass of penguins by species
    plt.figure(figsize=(10, 6))

    # Create the bar plot and assign to variable
    bar_plot = sns.barplot(
        x="species", y="body_mass_g", data=penguins, errorbar="sd", palette="Blues_d"
    )
    plt.title("Average Body Mass of Penguins by Species")
    plt.xlabel("Species")
    plt.ylabel("Body Mass (g)")

    # Use the user-facing API: maidr.render() with plot object
    logger.info("=== Using maidr.render() API ===")
    maidr_html = maidr.render(bar_plot)
    logger.info(f"Type of maidr.render(): {type(maidr_html)}")
    logger.info(f"String representation: {str(maidr_html)[:300]}...")

    # Check if the output contains iframe
    html_str = str(maidr_html)
    contains_iframe = "<iframe" in html_str.lower()
    logger.info(f"Contains iframe: {contains_iframe}")

    # Return the maidr HTML directly
    return str(maidr_html)

if __name__ == '__main__':
    logger.info("Starting Flask app with logging...")
    logger.info("Visit http://localhost:5002 to see the maidr plot in Flask")
    app.run(debug=False, host='0.0.0.0', port=5002)
