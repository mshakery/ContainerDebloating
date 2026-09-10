
## Replication command

From the repository root:

```
Rscript analysis/main.R
```

On Windows, if `Rscript` is not on `PATH`:

```
"C:\Program Files\R\R-4.6.1\bin\Rscript.exe" analysis/main.R
```

The script takes no arguments and uses only paths relative to the repository
root. It contains no absolute paths, host names, or credentials.

## Environment

R 4.6.1. The required packages are on CRAN and are installed with:

```r
install.packages(c(
  "dplyr", "tidyr", "readr", "purrr", "tibble", "stringr", "forcats",
  "ggplot2", "scales", "patchwork", "ggrepel", "ggbeeswarm", "ARTool"
))
```

| Package | Used for |
|---|---|
| dplyr, tidyr, readr, purrr, tibble, stringr, forcats | data preparation and tidy tables |
| ggplot2, scales, patchwork, ggrepel, ggbeeswarm | figures |
| ARTool | aligned rank transform for the two-factor models |

Friedman, Shapiro--Wilk, and Mann--Whitney come from base R `stats`. The exact
tied-aware signed-rank permutation test and the matched-pairs rank-biserial
correlation are implemented in `main.R` itself, so no effect-size package is
needed.
