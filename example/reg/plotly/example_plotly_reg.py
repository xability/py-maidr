import numpy as np
import plotly.graph_objects as go

import maidr

# Generate sample data with a linear trend
np.random.seed(42)
x = np.linspace(0, 10, 50)
y = 2.5 * x + 3 + np.random.normal(0, 2, 50)

# Compute linear regression
coeffs = np.polyfit(x, y, 1)
trend_y = np.polyval(coeffs, x)

# Create scatter plot with regression line
fig = go.Figure()
fig.add_trace(go.Scatter(x=x.tolist(), y=y.tolist(), mode="markers",
                         name="Data", marker=dict(color="steelblue")))
fig.add_trace(go.Scatter(x=x.tolist(), y=trend_y.tolist(), mode="lines",
                         name="Regression", line=dict(color="red", width=2)))
fig.update_layout(title="Scatter Plot with Regression Line",
                  xaxis_title="X", yaxis_title="Y")

maidr.show(fig)
