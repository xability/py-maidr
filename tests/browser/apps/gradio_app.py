"""A Gradio app with two accessible charts.

The first is placed when the app is built, with ``output_maidr``; the second
is filled, and replaced, by a slider's event handler returning
``render_maidr``. Both load the bundled ``maidr.js`` from inside their frame,
so the app needs no network.
"""

import matplotlib

matplotlib.use("Agg")

import gradio as gr  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from maidr.widget.gradio import output_maidr, render_maidr  # noqa: E402


def sales():
    fig, ax = plt.subplots()
    ax.bar(["north", "south", "east"], [4, 7, 5])
    ax.set_title("Sales by region")
    return ax


def bars(n):
    fig, ax = plt.subplots()
    ax.bar([f"b{i}" for i in range(int(n))], range(1, int(n) + 1))
    ax.set_title(f"{int(n)} bars")
    markup = render_maidr(ax, use_cdn=False)
    plt.close(fig)
    return markup


with gr.Blocks() as demo:
    output_maidr(sales(), use_cdn=False)
    count = gr.Slider(2, 6, value=3, step=1, label="Bars")
    chart = output_maidr()
    demo.load(bars, count, chart)
    count.change(bars, count, chart)

demo.launch()
