"""A Streamlit app that makes reruns countable.

``st.session_state`` survives a rerun, so the counter distinguishes "the
script ran again" from "the page looks slightly different" -- which is
all an ``innerText`` diff can tell, and it does not move on an otherwise
identical rerun.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import streamlit as st  # noqa: E402

from maidr.widget.streamlit import render_maidr  # noqa: E402

st.session_state["runs"] = st.session_state.get("runs", 0) + 1
st.markdown(f"RUNCOUNT={st.session_state['runs']}")

fig, ax = plt.subplots()
ax.bar(["a", "b", "c"], [1, 2, 3])
ax.set_title("Sales by region")
# Inlined so the runtime loads without network, as elsewhere in this suite.
render_maidr(ax, use_cdn=False)
plt.close(fig)
