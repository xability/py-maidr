import matplotlib.pyplot as plt
import seaborn as sns
import maidr

# Load dataset
diamonds = sns.load_dataset("diamonds")

print("Creating violin plot with 5 violins...")

# Create violin plot comparing price across cut quality
v = sns.violinplot(
    x="cut",            # 5 categories
    y="price",          # numeric values
    data=diamonds,
    inner="box",        # show box plot inside violin
    palette="Set2"      # distinct colors
)

# Customize the plot
plt.title("Diamond Price Distribution by Cut Quality")
plt.xlabel("Cut Quality")
plt.ylabel("Price (USD)")

print("Showing with MAIDR...")
maidr.show(v)
