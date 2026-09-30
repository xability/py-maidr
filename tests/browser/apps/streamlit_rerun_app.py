"""A Streamlit app whose chart is rendered afresh on every rerun (#460).

Deliberately uncached: ``render_maidr`` is called on a new figure each
run, the way the dashboards page shows it, so whether the frame survives a
rerun is decided by what ``render_maidr`` hands Streamlit and nothing else.

``Unrelated`` reruns the script without touching the chart; ``More data``
changes the chart, which has to reach the reader rather than be kept as
the chart they were already reading.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import streamlit as st  # noqa: E402

from maidr.widget.streamlit import render_maidr  # noqa: E402

st.session_state["runs"] = st.session_state.get("runs", 0) + 1
st.markdown(f"RUNCOUNT={st.session_state['runs']}")
st.checkbox("Unrelated")
more = st.checkbox("More data")

labels = ["a", "b", "c", "d"] if more else ["a", "b", "c"]
fig, ax = plt.subplots()
ax.bar(labels, range(1, len(labels) + 1))
ax.set_title("Sales by region")
# Inlined so the runtime loads without network, as elsewhere in this suite.
render_maidr(ax, use_cdn=False)
plt.close(fig)
