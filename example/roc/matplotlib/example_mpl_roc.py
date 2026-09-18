"""Read a scikit-learn `RocCurveDisplay` as a ROC curve.

Requires the optional extra: `pip install maidr[sklearn]`.

Every way scikit-learn draws a ROC curve -- `from_estimator`,
`from_predictions`, `from_cv_results`, or a hand-built display -- ends in
`RocCurveDisplay.plot()`, and that is what maidr reads. Each curve is its
false and true positive rates, the name the caller gave it, and the area the
display computed, so a reader hears the rate on the unit interval, the pan
following the false positive rate, and, in the description, the area under
each curve and the best operating point. Two displays plotted on one axes
are two curves of one chart, navigated with Up and Down.
"""

import matplotlib.pyplot as plt
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import RocCurveDisplay
from sklearn.model_selection import train_test_split

import maidr  # noqa: F401

X, y = make_classification(n_samples=400, n_informative=4, random_state=0)
X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=0)

fig, ax = plt.subplots()
for model in (LogisticRegression(max_iter=500), RandomForestClassifier(random_state=0)):
    model.fit(X_train, y_train)
    # Both curves land on one axes, so maidr reads them as one chart.
    RocCurveDisplay.from_estimator(model, X_test, y_test, ax=ax)

# The chance diagonal is a reference, not a curve; maidr leaves it out.
ax.plot([0, 1], [0, 1], linestyle="--", color="grey")
ax.set_title("ROC curves of two classifiers")

plt.show()
