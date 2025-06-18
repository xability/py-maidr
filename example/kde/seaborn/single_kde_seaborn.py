import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import maidr

# 1) Sample data
data = np.random.randn(500)

# 2) Plot the KDE curve
ax = sns.kdeplot(data)
plt.xlabel("Value")
plt.ylabel("Density")
plt.title("Seaborn KDE Plot")
plt.tight_layout()
maidr.show(ax)
