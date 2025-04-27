python3 -m pyperf timeit \
    --name "example_mpl_box" \
    --setup "from benchmarks.box.matplotlib.example_mpl_box import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_sns_box" \
    --setup "from benchmarks.box.seaborn.example_sns_box import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_mpl_line" \
    --setup "from benchmarks.line.matplotlib.example_mpl_line import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_sns_line" \
    --setup "from benchmarks.line.seaborn.example_sns_line import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_mpl_dodged" \
    --setup "from benchmarks.dodged.example_mpl_dodged import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_mpl_multilayer" \
    --setup "from benchmarks.multilayer.example_mpl_multilayer import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_mpl_multipanel" \
    --setup "from benchmarks.multipanel.matplotlib.example_mpl_multipanel import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_sns_multipanel" \
    --setup "from benchmarks.multipanel.seaborn.example_sns_multipanel import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_mpl_scatter" \
    --setup "from benchmarks.scatter.matplotlib.example_mpl_scatter import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"


python3 -m pyperf timeit \
    --name "example_sns_scatter" \
    --setup "from benchmarks.scatter.seaborn.example_sns_scatter import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_mpl_hist" \
    --setup "from benchmarks.histogram.matplotlib.example_mpl_hist import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"


python3 -m pyperf timeit \
    --name "example_mpl_stacked" \
    --setup "from benchmarks.stacked.matplotlib.example_mpl_stacked import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_sns_stacked" \
    --setup "from benchmarks.stacked.seaborn.example_sns_stacked import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"


python3 -m pyperf timeit \
    --name "example_mpl_heatmap" \
    --setup "from benchmarks.heatmap.matplotlib.example_mpl_heatmap import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_mpl_heatmap" \
    --setup "from benchmarks.heatmap.matplotlib.example_mpl_heatmap import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_sns_heatmap" \
    --setup "from benchmarks.heatmap.seaborn.example_sns_heatmap import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_mpl_multiline" \
    --setup "from benchmarks.multiline.matplotlib.example_mpl_multiline import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_sns_multiline" \
    --setup "from benchmarks.multiline.seaborn.example_sns_multiline import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_seaborn_dodged" \
    --setup "from benchmarks.dodged.example_seaborn_dodged import test" \
    --loops 1 \
    --values 1000 \
    --warmups 3 \
    --processes 1 \
    "test()"

python3 -m pyperf timeit \
    --name "example_sns_multilayer" \
    --setup "from benchmarks.multilayer.example_sns_multilayer import test" \
    --loops 1 \
    --values 100 \
    --warmups 3 \
    --processes 1 \
    "test()"
