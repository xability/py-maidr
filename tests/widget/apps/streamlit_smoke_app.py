"""A minimal Streamlit app, driven by ``AppTest`` in the widget tests.

Kept as a file rather than a string so ``AppTest.from_file`` runs it the
way Streamlit runs a real script.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.widget.streamlit import render_maidr  # noqa: E402

fig, ax = plt.subplots()
ax.bar(["a", "b"], [1, 2])
render_maidr(ax, use_cdn=True)
