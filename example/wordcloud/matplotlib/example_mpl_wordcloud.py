"""Read a `wordcloud.WordCloud` shown with `imshow` as a word cloud.

Requires the optional extra: `pip install maidr[wordcloud]`.

A word cloud draws each term's weight as glyph size and writes it down
nowhere, so the reading is a term and its number. `WordCloud` normalises
every frequency by the largest one and keeps only the ratio, which is why
the weight axis is named "Share of mentions" rather than a count.
"""

import matplotlib.pyplot as plt
from wordcloud import WordCloud

import maidr  # noqa: F401

# Raw counts. `generate_from_frequencies` divides these by the largest, so
# maidr announces 1.0, 0.728, 0.607 ... rather than 412, 300, 250.
mentions = {
    "accessibility": 412,
    "sonification": 300,
    "braille": 250,
    "screenreader": 190,
    "keyboard": 155,
    "contrast": 120,
    "captions": 95,
    "semantics": 70,
}

# Pass the `WordCloud` object itself. `wc.to_array()` and `wc.to_image()`
# hand `imshow` a plain RGB array with the terms nowhere in it, and such a
# figure stays an unread picture.
cloud = WordCloud(
    width=800,
    height=400,
    background_color="white",
    max_words=8,
    random_state=42,
).generate_from_frequencies(mentions)

fig, ax = plt.subplots(figsize=(8, 4))

# A cloud has no x or y scale -- the glyph positions are packing, not data --
# so the axis labels name what a point holds rather than where it sits.
ax.set_xlabel("Topic")
ax.set_ylabel("Share of mentions")
ax.set_title("What the accessibility reports talk about")

ax.imshow(cloud)
ax.set_axis_off()

plt.show()
