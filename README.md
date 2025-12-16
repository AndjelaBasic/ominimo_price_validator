This readme contains details on probelm statement and proposed solution as well as instructions on how to run the code.

# 1. Instructions on how to run the code
## Environment

- **Python**: 3.12.8
- **pip**: 25.3

## Setup (run below commands from the project root one by one; this is for Windows)
```
python -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip

pip install -r requirements.txt
```

## Run tests (from the project root)
```python -m pytest -q```

## Run main (from the project root)
```python -m src.main```

# 2. Problem statement and proposed solution
## Problem Statement

We are given a dictionary of insurance prices keyed by product identifiers, e.g.

- `mtpl`
- `limited_casco_<variant>_<deductible>`
- `casco_<variant>_<deductible>`

where:

- **Product type** in {MTPL, Limited Casco, Casco}
- **Variant** in {compact, basic, comfort, premium}
- **Deductible** in {100, 200, 500}

The task is to **validate** and **automatically fix** pricing inconsistencies according to business rules and reference pricing structure.

The solution must:
- Detect and report violations 
- Fix prices deterministically
 
## Pricing Rules

### 1. Product-Type Ordering

Prices must satisfy:

- **MTPL < Limited Casco < Casco**

This is enforced in two ways:

#### 1.1 MTPL vs Group Minima

For each product group:

- `MTPL < min(Limited Casco)`
- `MTPL < min(Casco)`

#### 1.2 Limited Casco vs Casco (all else equal)

For matching `(variant, deductible)` combinations:
- `limited_casco(v, d) < casco(v, d)`

### 2. Deductible Ordering

Within each `(product, variant)`: 
- `price(100) > price(200) > price(500)`
- Higher deductible lowers price.

### 3. Variant Ordering

Within each `(product, deductible)`:
- `base := max(price(compact), price(basic))`
- `base < comfort < premium`

## Proposed Solution

The solution is implemented as an **iterative validation–repair engine** with three clearly separated concerns:

1. **Parsing** – convert raw keys into structured `PricingItem` 
2. **Validation** – detect violations without modifying prices  
3. **Fixing** – apply deterministic repairs *only when rules are violated*

The engine repeatedly applies fixes until:
- No further violations are detected, or
- A maximum iteration limit is reached

### Validation
Exactly as described in pricing rules, without modifying prices.

### Fixing

### 1. MTPL Anchor

MTPL is used as the global anchor **unless it is an outlier** relative to other products.

If MTPL is too far from the scale impled by average prices of Limited Casco and Casco, it is rebased using:
- `mtpl := 400 × median(scale_factors)`
- This prevents MTPL from destabilizing all other prices.

### 2. Product-Type Fixes

#### 2.1 MTPL vs Group Minima
- If violated, compute target minima as `MTPL*factor`, where factor is derived from average prices. 
- Then, scale each product group by the `new_minima/old_minima` factor such that relative distances are preserved.

#### 2.2 Limited Casco vs Casco (Matched)
If violated, `casco := (9 / 7) × limited_casco`.

### 3. Deductible Fixing

Within `(product, variant)`, if **any** deductible ordering violation exists, rebuild the entire ladder from the 100€ base:
- `price(200) := 0.9 × price(100)`
- `price(500) := 0.8 × price(100)`


### 4. Variant Fixing

Within `(product, deductible)`, define: `base = max(compact, basic)`. 

If **any** variant ordering violation exists, rebuild the entire variant ladder:
  - `comfort := 1.07 × base`
  - `premium := 1.14 × base`

3, 4 rebuild entire ladder to avoid partial fixes that could introduce new violations.

## Key Design Choices

- **Separation of concerns**: parsing, validation, fixing
- **Only-if-violated fixes**: preserves valid inputs
- **Uses available averages for fixing inconsistencies**: inconsistencies are fixed according to the provided averages, not randomly

