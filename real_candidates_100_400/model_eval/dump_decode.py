"""Compact decode table for REPORT."""
import json

ME = "/home/shokha/vliw-ai-scheduler-demo/real_candidates_100_400/model_eval"
res = json.load(open(ME + "/results.json"))
dec = json.load(open(ME + "/decode.json"))
order = (["poly_covariance", "poly_gemm", "tsvc_s1111", "poly_adi",
          "poly_gesummv", "emb_iir", "poly_floyd_int", "poly_heat3d",
          "poly_gramschmidt", "poly_fdtd", "emb_fir", "poly_jacobi2d",
          "poly_symm"]
         + ["poly_syrk", "poly_trmm", "poly_durbin", "poly_trisolv_int",
            "poly_seidel", "poly_jacobi1d", "poly_gemver", "poly_lu",
            "oblas_gemv", "cm_mul", "cm_bitextract", "cm_vect"])
print(f"{'graph':20s} {'ptok':>5s} {'otok':>5s} {'t(s)':>6s} "
      f"{'lines':>5s} {'match':>5s} {'place':>5s} {'extra':>5s} "
      f"{'dup':>4s} {'miss':>4s} {'badln':>5s} {'cut':>3s} {'trunc':>5s} "
      f"{'raw':>7s} {'winner':>14s}")
for g in order:
    r = res[g]
    d = dec[g]
    meta = json.load(open(f"{ME}/raw/{g}.meta.json"))
    raw = r["raw"]
    print(f"{g:20s} {meta['prompt_tokens']:5d} {meta['out_tokens']:5d} "
          f"{meta['gen_s']:6.0f} {d['n_lines']:5d} {d['n_matched_unique']:5d} "
          f"{raw['placed']:5d} {d['n_extra_ids']:5d} {d['n_dup_ids']:4d} "
          f"{d['n_missing']:4d} {str(d['first_bad_line']):>5s} "
          f"{str(d['cut_midline']):>3s} {str(d['ctx_truncated']):>5s} "
          f"{str(raw['makespan']):>7s} {r['L3_portfolio_winner']:>14s}")
