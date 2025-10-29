# Quick Test: Violin Plot Density Display

## ✅ Python Backend - WORKING
The test confirms that density is being calculated:
- ✓ Density field found in data
- ✓ 203/203 points have density > 0
- ✓ Sample values show correct density calculations

## Frontend Testing

### Step 1: Build the Frontend (if needed)
```bash
cd maidr
npm install  # if needed
npm run build  # or your build command
```

### Step 2: Open the HTML File
Open `py-maidr/violin_density_test.html` in your web browser.

### Step 3: Navigate and Verify
- Use **arrow keys** (← →) to navigate through the plot
- The text output should show: **"X is [x], Y is [y], Width is [density]"**
- Check the console for any JavaScript errors

### Expected Output
When navigating the violin plot, you should see text like:
- **Verbose mode**: "X is 0.0007, Y is -2.86, Width is 0.0014"
- **Terse mode**: "0.0007, -2.86, Width is 0.0014"

## Troubleshooting

If width is not showing:

1. **Check browser console** for JavaScript errors
2. **Verify frontend is rebuilt** - the TypeScript changes need to be compiled
3. **Check the HTML file** contains the latest MAIDR JavaScript bundle
4. **Inspect the data** - open browser dev tools and check if density is in the MAIDR data object

## Manual Verification

You can also manually check the JSON in the HTML file:
1. Open `violin_density_test.html` in a text editor
2. Search for `"density"` - you should find entries like:
   ```json
   {"x": 0.0007, "y": -2.86, "density": 0.0014, ...}
   ```

If density is in the JSON but not displaying, the frontend code needs to be rebuilt.

