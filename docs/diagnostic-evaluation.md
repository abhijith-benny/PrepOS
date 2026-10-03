# Diagnostic Evaluation

Generated on 2026-09-20 with seed `7` and 1,500 synthetic learners. The evaluation uses 100 learners for adaptive-vs-fixed question recovery so the test remains practical on a developer machine. The clustering metrics use all 1,500 learners.

## Estimation method

The engine uses an independent Beta posterior per topic, initialized as Beta(1, 1). A correct answer increments alpha and an incorrect answer increments beta. Mastery is the posterior mean, `alpha / (alpha + beta)`, and uncertainty is `1 / (alpha + beta)`. Beta was selected because it is bounded to [0, 1], updates online after each binary answer, and exposes a direct uncertainty signal for adaptive selection.

## Results

| Metric | Adaptive | Fixed random |
|---|---:|---:|
| Mastery MAE | 0.170168 | 0.349042 |
| Spearman correlation | 0.270294 | 0.218291 |
| Mean questions to confidence/limit | 25.000000 | n/a |
| Maximum questions | 25 | n/a |

The current configuration reaches the 25-question maximum before the confidence threshold because the diagnostic covers 25 topics and requires one answer per topic. The stopping rule is implemented and tested, but the default configuration does not reach the threshold earlier.

## Clustering

The model compared KMeans and GaussianMixture for k in {4, 5, 6}. Selection used silhouette score first, then preferred KMeans on an exact score tie. The selected model is KMeans with 5 clusters.

- Selected silhouette: `0.503034`
- Cluster sizes: `0=301`, `1=315`, `2=296`, `3=295`, `4=293`
- Five-seed silhouette scores: `0.503034`, `0.503034`, `0.503034`, `0.503034`, `0.503034`
- Five-seed mean: `0.503034`
- Five-seed minimum: `0.503034`
- Model version: `diagnostic-profile-v1`

The true-archetype to assigned-cluster counts were:

| True archetype | Cluster 0 | Cluster 1 | Cluster 2 | Cluster 3 | Cluster 4 |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 296 | 0 | 0 |
| 1 | 0 | 0 | 0 | 295 | 0 |
| 2 | 301 | 0 | 0 | 0 | 0 |
| 3 | 0 | 0 | 0 | 0 | 293 |
| 4 | 0 | 315 | 0 | 0 | 0 |

## Review decisions

- The Beta posterior is simple and online, but the current confidence measure is conservative and coverage-driven. Review whether 25 topics should remain mandatory or whether the production diagnostic should use fewer topic groups with repeated questions.
- Generated seed questions in `supabase/seed_questions.sql` are explicitly placeholders and require manual domain review before use.
- Profile labels are derived from centroid group means. They are not hard-coded per cluster ID, so cluster IDs may change between model retrains while labels remain interpretable.
- The generated joblib model is loaded at diagnostic-module startup and carries the version string above.
