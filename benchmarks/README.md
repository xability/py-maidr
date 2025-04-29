# Benchmarks

The `benchmarks` folder contains scripts and configurations to measure and analyze the performance of various plots in the py-maidr project.

## Contents
- `<< plots >>`: Contains various example plots supported by maidr
- `script.sh`: Shell script to automate running all benchmark tests and collecting performance metrics.

## Prerequisites

- Python 3.x
- Project dependencies installed (from project root run `pip install -r requirements.txt`)
- Bash shell (for `script.sh`)
- PyPerf (https://pypi.org/project/pyperf/)

## Running the Benchmark Script

1. Change into the benchmarks directory:
   ```bash
   cd /Users/dakshpokar/RA/py-maidr/benchmarks
   ```
2. Execute the script:
   ```bash
   ./script.sh
   ```

## Example

```bash
cd benchmarks
chmod +x script.sh
./script.sh
```
