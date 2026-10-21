# -*- coding: utf-8 -*-
"""Обучение блоков по той же схеме, по которой работает ядро (numpy, градиенты вручную, без torch).

Один шаг — пакет вопросов через всю сеть, ровно как в ядре:
  проход 1: каждый присутствующий блок пишет оценки своих понятий c = L·tanh((h·A + a)/L);
  смешивание по формуле схемы (среднее или сумма по присутствующим писателям) → шина m и признаки присутствия π;
  проход 2: каждый блок даёт счёты своих ответов s = h·U + [m, π]·V + b (читает только понятия из «читает»);
  сборка: softmax по [«ничего» = 0, счёты всех присутствующих блоков].
Потери: перекрёстная энтропия ответа + λ · логистическая потеря для каждого понятия, которое пишет каждый присутствующий блок
(язык требует, чтобы число каждого писателя само было откалиброванным логарифмом шансов).
«Выходные»: в каждом примере каждый блок отсутствует с вероятностью p_выходной; ответы отсутствующего блока исчезают из
softmax, его вклады — со шины; если верный ответ принадлежит отсутствующему блоку, цель — «ничего».
Замороженные блоки считаются, но их числа не меняются (Adam к ним не применяется)."""
import json
import os
import sys
import time

import numpy as np

V8 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(V8, "архитектуры"))
import мешок_шина as МШ  # noqa: E402

BIG = -1e30


class БлокУч:
    def __init__(self, имя, ответы, пишет, читает, корзины=1 << 17, размер=64, граница=8.0, соль=None, seed=1,
                 init=None, заморожен=False, область="", роль="", свёртка="корень", масштаб_чтения=1.0):
        self.имя, self.область, self.роль = имя, область, роль
        self.свёртка = свёртка          # «корень»: h = сумма векторов / √n; «среднее»: h = сумма / n
        self.масштаб = float(масштаб_чтения)   # блок читает число шины, делённое на масштаб
        self.ответы, self.пишет, self.читает = list(ответы), list(пишет), list(читает)
        self.B, self.d, self.L = int(корзины), int(размер), float(граница)
        self.соль = соль or имя.split("@")[0]
        self.заморожен = заморожен
        rng = np.random.RandomState(seed)
        W, R, Y = len(self.пишет), len(self.читает), len(self.ответы)
        if init is None:
            self.P = {"E": rng.uniform(-0.1, 0.1, (self.B, self.d)).astype(np.float32),
                      "A": (rng.randn(self.d, W) * 0.01).astype(np.float32), "a": np.zeros(W, np.float32),
                      "U": (rng.randn(self.d, Y) * 0.01).astype(np.float32), "b": np.zeros(Y, np.float32),
                      "V": np.zeros((2 * R, Y), np.float32)}
        else:
            self.P = {k: np.array(init[k], dtype=np.float32) for k in ("E", "A", "a", "U", "V", "b")}
        self.M = {k: np.zeros_like(v) for k, v in self.P.items()} if not заморожен else None
        self.S = {k: np.zeros_like(v) for k, v in self.P.items()} if not заморожен else None

    def индексы(self, токены):
        return МШ.индексы(self.соль, токены, self.B).astype(np.int32)

    def чисел(self):
        return int(sum(v.size for v in self.P.values()))

    def сохранить(self, путь):
        with open(путь, "wb") as f:
            np.savez(f, **self.P, пишет=np.array(self.пишет, dtype=str), читает=np.array(self.читает, dtype=str),
                     ответы=np.array(self.ответы, dtype=str))


class Набор:
    """Вопросы, переведённые на язык: для каждого блока — номера токенов (свои корзины), цели-ответы, метки понятий."""

    def __init__(self, rows, блоки, понятия_языка, группа=None):
        self.n = len(rows)
        self.группа = [r.get("группа", группа) for r in rows]
        self.ответы = [r["ответы"] for r in rows]
        self.ki = {k: j for j, k in enumerate(понятия_языка)}
        Y = np.full((self.n, len(понятия_языка)), np.nan, np.float32)
        for i, r in enumerate(rows):
            for k, y in r["понятия"].items():
                if y is not None and k in self.ki:
                    Y[i, self.ki[k]] = y
        self.метки = Y
        self.ток = {}
        for b in блоки:
            self.добавить_блок(b, rows)

    def добавить_блок(self, b, rows):
        key = (b.соль, b.B)
        if key in self.ток:
            return
        lens = np.array([len(r["токены"]) for r in rows], np.int64)
        flat = np.concatenate([b.индексы(r["токены"]) for r in rows]) if self.n else np.zeros(0, np.int32)
        off = np.zeros(self.n + 1, np.int64)
        np.cumsum(lens, out=off[1:])
        self.ток[key] = (flat, off, lens)

    def пакет(self, b, idx_rows):
        flat, off, lens = self.ток[(b.соль, b.B)]
        L = lens[idx_rows]
        parts = [flat[off[r]:off[r + 1]] for r in idx_rows]
        return np.concatenate(parts).astype(np.int64), L


class Сеть:
    """Блоки + схема (проходов, смешивание, веса). Считает пакеты ровно как ядро."""

    def __init__(self, блоки, проходов=2, смешивание="среднее", веса_смешивания=None, градиент_через_шину=True, шум_шины=0.0):
        """градиент_через_шину=False: писатели учатся только по потере языка (их числа значат ровно то, что сказано в языке,
        а не скрытый код для соседа); шум_шины — σ гауссова шума на числах шины при обучении (только при обучении)."""
        self.градиент_через_шину = градиент_через_шину
        self.шум_шины = float(шум_шины)
        self.rng_шум = np.random.RandomState(12345)
        self.блоки = блоки
        self.dt = блоки[0].P["E"].dtype
        self.проходов = проходов
        self.смешивание = смешивание
        self.w = np.array([float((веса_смешивания or {}).get(b.имя, 1.0)) for b in блоки], self.dt)
        self.K = []
        for b in блоки:
            for k in b.пишет:
                if k not in self.K:
                    self.K.append(k)
        self.Ki = {k: j for j, k in enumerate(self.K)}
        self.cols, self.все_ответы, start = [], [], 1
        for b in блоки:
            self.cols.append(np.arange(start, start + len(b.ответы)))
            start += len(b.ответы)
            self.все_ответы += b.ответы
        self.ai = {a: j + 1 for j, a in enumerate(self.все_ответы)}
        self.хозяин = np.zeros(start, np.int64)
        for i, c in enumerate(self.cols):
            self.хозяин[c] = i
        self.t = 0
        self.dt = блоки[0].P["E"].dtype

    # -------------------------------------------------------------- прямой проход
    def вперёд(self, набор, rows, M, обучение=False):
        n = len(rows)
        cache = {"n": n, "M": M, "rows": rows, "h": [], "z": [], "c": [], "idx": [], "lens": [], "X": [], "s": []}
        for i, b in enumerate(self.блоки):
            idx, lens = набор.пакет(b, rows)
            starts = np.zeros(n, np.int64)
            np.cumsum(lens[:-1], out=starts[1:])
            G = b.P["E"][idx]
            norm = np.sqrt(lens) if b.свёртка == "корень" else lens
            h = np.add.reduceat(G, starts, axis=0) / norm[:, None].astype(self.dt)
            z = h @ b.P["A"] + b.P["a"]
            c = b.L * np.tanh(z / b.L)
            for key, v in (("h", h), ("z", z), ("c", c), ("idx", idx), ("lens", lens)):
                cache[key].append(v)
        nK = len(self.K)
        num = np.zeros((n, nK), self.dt)
        den = np.zeros((n, nK), self.dt)
        for i, b in enumerate(self.блоки):
            for jw, k in enumerate(b.пишет):
                col = self.Ki[k]
                num[:, col] += M[:, i] * self.w[i] * cache["c"][i][:, jw]
                den[:, col] += M[:, i] * self.w[i]
        if self.смешивание == "среднее":
            m = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
        else:
            m = num
        pi = (den > 0).astype(self.dt)
        cache.update(m=m, pi=pi, den=den)
        if обучение and self.шум_шины > 0:
            m = m + (self.шум_шины * self.rng_шум.randn(*m.shape)).astype(self.dt) * pi
        logits = np.full((n, len(self.хозяин)), BIG, self.dt)
        logits[:, 0] = 0.0
        for i, b in enumerate(self.блоки):
            s = cache["h"][i] @ b.P["U"] + b.P["b"]
            X = None
            if self.проходов == 2 and b.читает:
                rc = [self.Ki[k] for k in b.читает if k in self.Ki]
                X = np.zeros((n, 2 * len(b.читает)), self.dt)
                for j, k in enumerate(b.читает):
                    if k in self.Ki:
                        X[:, j] = m[:, self.Ki[k]] / b.масштаб
                        X[:, len(b.читает) + j] = pi[:, self.Ki[k]]
                s = s + X @ b.P["V"]
            cache["X"].append(X)
            cache["s"].append(s)
            pres = M[:, i] > 0
            logits[:, self.cols[i]] = np.where(pres[:, None], s, BIG)
        mx = logits.max(1, keepdims=True)
        e = np.exp(logits - mx)
        p = e / e.sum(1, keepdims=True)
        cache["p"] = p
        return p, cache

    def цели(self, набор, rows, M):
        n = len(rows)
        T = np.zeros((n, len(self.хозяин)), self.dt)
        for r, row in enumerate(rows):
            ids = [self.ai[a] for a in набор.ответы[row] if a in self.ai]
            ids = [j for j in ids if M[r, self.хозяин[j]] > 0]
            if ids:
                T[r, ids] = 1.0 / len(ids)
            else:
                T[r, 0] = 1.0
        return T

    # -------------------------------------------------------------- шаг обучения
    def градиенты(self, набор, rows, M, λ=1.0):
        """Потери и градиенты пакета (ничего не меняет). Возвращает (потеря ответа, потеря понятий, [градиенты блоков])."""
        p, C = self.вперёд(набор, rows, M, обучение=True)
        T = self.цели(набор, rows, M)
        n = len(rows)
        loss = float(-(T * np.log(np.clip(p, 1e-12, 1.0))).sum() / n)
        dlog = (p - T) / n
        grads, dh_all = [], []
        dm = np.zeros_like(C["m"])
        for i, b in enumerate(self.блоки):
            ds = dlog[:, self.cols[i]] * M[:, i:i + 1]
            g = {"U": C["h"][i].T @ ds, "b": ds.sum(0)}
            dh = ds @ b.P["U"].T
            X = C["X"][i]
            if X is not None:
                g["V"] = X.T @ ds
                dX = ds @ b.P["V"].T
                for j, k in enumerate(b.читает):
                    if k in self.Ki:
                        dm[:, self.Ki[k]] += dX[:, j] / b.масштаб
            else:
                g["V"] = np.zeros_like(b.P["V"])
            grads.append(g)
            dh_all.append(dh)
        aux = 0.0
        safe_den = np.where(C["den"] > 0, C["den"], 1.0)
        for i, b in enumerate(self.блоки):
            g = grads[i]
            if not b.пишет:
                g["A"] = np.zeros_like(b.P["A"])
                g["a"] = np.zeros_like(b.P["a"])
                continue
            c = C["c"][i]
            dc = np.zeros_like(c)
            sig = 1.0 / (1.0 + np.exp(-c))
            for jw, k in enumerate(b.пишет):
                col = self.Ki[k]
                if not self.градиент_через_шину:
                    pass
                elif self.смешивание == "среднее":
                    dc[:, jw] += dm[:, col] * M[:, i] * self.w[i] / safe_den[:, col]
                else:
                    dc[:, jw] += dm[:, col] * M[:, i] * self.w[i]
                if k in набор.ki:
                    y = набор.метки[rows, набор.ki[k]]
                    mask = (~np.isnan(y)) & (M[:, i] > 0)
                    yy = np.where(mask, y, 0.0)
                    dc[:, jw] += λ * (sig[:, jw] - yy) * mask / n
                    q = np.clip(sig[:, jw], 1e-7, 1 - 1e-7)
                    aux += float(-(mask * (yy * np.log(q) + (1 - yy) * np.log(1 - q))).sum() / n)
            th = np.tanh(C["z"][i] / b.L)
            dz = dc * (1.0 - th * th)
            g["A"] = C["h"][i].T @ dz
            g["a"] = dz.sum(0)
            dh_all[i] = dh_all[i] + dz @ b.P["A"].T
        for i, b in enumerate(self.блоки):
            idx, lens = C["idx"][i], C["lens"][i]
            norm = np.sqrt(lens) if b.свёртка == "корень" else lens
            dG = np.repeat(dh_all[i] / norm[:, None].astype(self.dt), lens, axis=0)
            order = np.argsort(idx, kind="stable")
            sidx = idx[order]
            bounds = np.flatnonzero(np.r_[True, sidx[1:] != sidx[:-1]])
            grads[i]["E"] = (sidx[bounds], np.add.reduceat(dG[order], bounds, axis=0))
        return loss, λ * aux, grads

    def применить(self, grads, lr, b1=0.9, b2=0.999, eps=1e-8):
        self.t += 1
        bc1, bc2 = 1 - b1 ** self.t, 1 - b2 ** self.t
        for b, g in zip(self.блоки, grads):
            if b.заморожен:
                continue
            for k in ("A", "a", "U", "V", "b"):
                if b.P[k].size == 0:
                    continue
                b.M[k] = b1 * b.M[k] + (1 - b1) * g[k]
                b.S[k] = b2 * b.S[k] + (1 - b2) * g[k] * g[k]
                b.P[k] -= (lr * (b.M[k] / bc1) / (np.sqrt(b.S[k] / bc2) + eps)).astype(self.dt)
            uniq, gE = g["E"]
            mE = b1 * b.M["E"][uniq] + (1 - b1) * gE
            sE = b2 * b.S["E"][uniq] + (1 - b2) * gE * gE
            b.M["E"][uniq], b.S["E"][uniq] = mE, sE
            b.P["E"][uniq] -= (lr * (mE / bc1) / (np.sqrt(sE / bc2) + eps)).astype(self.dt)

    def шаг(self, набор, rows, M, lr, λ=1.0):
        loss, aux, grads = self.градиенты(набор, rows, M, λ)
        self.применить(grads, lr)
        return loss, aux

    # -------------------------------------------------------------- оценка
    def предсказать(self, набор, rows=None, M=None, пакет=512):
        rows = np.arange(набор.n) if rows is None else np.asarray(rows)
        out = []
        for s in range(0, len(rows), пакет):
            r = rows[s:s + пакет]
            MM = np.ones((len(r), len(self.блоки)), self.dt) if M is None else M[s:s + пакет]
            p, _ = self.вперёд(набор, r, MM)
            out.append(p)
        return np.concatenate(out) if out else np.zeros((0, len(self.хозяин)), self.dt)

    def точность(self, набор, M=None):
        """Доля верных первых ответов среди «ничего» + ответов всех блоков (все блоки на месте), по группам."""
        p = self.предсказать(набор, M=M)
        top = p.argmax(1)
        res = {}
        for r in range(набор.n):
            ids = {self.ai[a] for a in набор.ответы[r] if a in self.ai} or {0}
            g = набор.группа[r]
            ok = int(top[r] in ids)
            res.setdefault(g, [0, 0])
            res[g][0] += ok
            res[g][1] += 1
        acc = {g: v[0] / v[1] for g, v in res.items()}
        return acc, float(np.mean(list(acc.values())))


def маска_выходных(n, nb, p_off, rng, заморожены=None):
    M = np.ones((n, nb), np.float32)
    if p_off <= 0 or nb < 2:
        return M
    M = (rng.rand(n, nb) >= p_off).astype(np.float32)
    empty = M.sum(1) == 0
    if empty.any():
        M[np.flatnonzero(empty), rng.randint(0, nb, empty.sum())] = 1.0
    return M


def обучить(сеть, набор, dev, эпох=15, терпение=3, пакет=64, lr=0.004, λ=1.0, p_выходной=0.3, seed=1, журнал=None, имя=""):
    rng = np.random.RandomState(seed)
    nb = len(сеть.блоки)
    best, best_score, bad, ход = None, -1.0, 0, []
    t0 = time.time()
    for ep in range(эпох):
        order = rng.permutation(набор.n)
        tl, ta, steps = 0.0, 0.0, 0
        for s in range(0, len(order), пакет):
            rows = order[s:s + пакет]
            M = маска_выходных(len(rows), nb, p_выходной, rng)
            l, a = сеть.шаг(набор, rows, M, lr, λ)
            tl += l
            ta += a
            steps += 1
        acc, score = сеть.точность(dev)
        rec = {"эпоха": ep + 1, "потеря": round(tl / steps, 4), "понятия": round(ta / steps, 4), "dev": round(score, 4),
               "dev_группы": {g: round(v, 4) for g, v in sorted(acc.items())}, "с": round(time.time() - t0, 1)}
        ход.append(rec)
        print("%s %s" % (имя, json.dumps(rec, ensure_ascii=False)), flush=True)
        if журнал:
            with open(журнал, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(rec, имя=имя), ensure_ascii=False) + "\n")
        if score > best_score:
            best_score, bad = score, 0
            best = [{k: v.copy() for k, v in b.P.items()} for b in сеть.блоки]
        else:
            bad += 1
            if bad >= терпение:
                break
    for b, P in zip(сеть.блоки, best):
        if not b.заморожен:
            b.P = P
    return {"эпох": len(ход), "лучший_dev": round(best_score, 4), "ход": ход, "время_с": round(time.time() - t0, 1)}
