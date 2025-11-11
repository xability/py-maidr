import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
import maidr

# Create a bimodal dataset
np.random.seed(42)
# Combine two normal distributions to create bimodality
data_bimodal = np.concatenate([
    np.random.normal(30, 5, 150),
    np.random.normal(60, 7, 150)
])

# Create a DataFrame
df = pd.DataFrame({"Score": data_bimodal})

print("Creating bimodal violin plot...")
# Create a violin plot showing bimodal distribution
v = sns.violinplot(y=df["Score"], inner='box', color="skyblue")

# Customize the plot
plt.title("Bimodal Distribution of Scores")
plt.ylabel("Score")
plt.xlabel("")

print("Showing with MAIDR...")
# Show with MAIDR accessibility
maidr.show(v)
