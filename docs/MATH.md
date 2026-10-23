# TIDELIGHT mathematics

This document describes the equations that drive the cinematic extension and
the separate equations/metrics used by the original inverse-rendering test.
The cinematic water and mist are deliberately compact procedural models. They
are useful because every change is inspectable and replayable; they are not a
claim of a full fluid or atmospheric simulation.

## Moving water

At time $t$, each water vertex at its baseline coordinates $(x,y)$ receives
the height

$$
\eta(x,y,t) = \sum_{i=1}^{4} A_i
\sin\left(k_{x,i}x+k_{y,i}y-\sqrt{g\lvert\mathbf{k}_i\rvert}\,(0.42t)+\phi_i\right),
$$

where

$$
\lvert\mathbf{k}_i\rvert=\sqrt{k_{x,i}^2+k_{y,i}^2},\qquad g=9.81.
$$

The square-root term is a dispersion-inspired angular frequency. The factor
0.42 is an explicitly chosen artistic time scale, so this should not be read
as a calibrated sea-state model.

| term | $A_i$ | $k_{x,i}$ | $k_{y,i}$ | $\phi_i$ |
|---|---:|---:|---:|---:|
| 1 | 0.090 | 0.42 | 0.095 | 0.25 |
| 2 | 0.042 | 0.93 | -0.16 | 1.70 |
| 3 | 0.020 | 1.80 | 0.41 | -0.80 |
| 4 | 0.012 | -0.72 | 1.12 | 2.35 |

The handler sets `vertex.co.z = eta(...)` from the cached baseline each frame;
it does not accumulate displacement. The water object keeps its world-space
offset of -0.04 scene units. The mesh has 21,901 vertices. A separate shader
mapping drifts fine normals by

$$
\Delta u(t)=t(0.065,-0.023,0).
$$

The normal drift is a material detail layer. It is not a second free-surface
solver.

## Mist field

The volume uses Blender Generated coordinates $g=(g_x,g_y,g_z)$. Define

$$
q=\operatorname{diag}(0.85,0.85,1.05)g+t(0.075,0.030,0),
$$

and let $N(q)$ be 3-D procedural noise with Scale 2.2, Detail 4 and
Roughness 0.66. A clamped color-ramp multiplier is

$$
R(N)=0.18+1.10\operatorname{clip}\left(\frac{N-0.18}{0.60},0,1\right).
$$

The density is

$$
D(g,t)=D_0\,H(g_z)\,R(N(q)),
$$

where $D_0=0.028$ is the selected base density and $H(g_z)$ is a
clamped height falloff mapping Generated $z=0\ldots1$ to
$0.65\ldots0.03$.
The volume color is `(0.68, 0.80, 0.96)`.

This is a moving procedural density field. It is not Navier–Stokes, a smoke
solver, or a measured wind field; the drift vector is an authored scene
parameter.

## Wet stone

For a foreground stone with world height $z$, define

$$
u=\operatorname{clip}\left(\frac{z+0.30}{1.50},0,1\right).
$$

The material maps $u$ to

$$
\operatorname{roughness}=0.11+0.47u,
\qquad
\operatorname{coat}=0.42-0.30u.
$$

Lower stones therefore receive a smoother, more coated wet look. Procedural
micrograin uses Noise Scale 260, Detail 2.5, Roughness 0.42, Bump Strength
0.16 and Bump Distance 0.012 scene units. The mapping is a shading rule, not a
waterline measurement.

## Camera rail

Let $p=\operatorname{clip}(t/10,0,1)$ and

$$
s=p^2(3-2p).
$$

The camera location is

$$
C(t)=(1.25s,\,-18.5+3s,\,1.42+0.08\sin(\pi p)),
$$

and the look-at target is

$$
T(t)=(0.85s,\,28+3s,\,0.35+0.08\sin(\pi p)).
$$

The camera uses a 32.5 mm lens, $f/7.1$ depth of field and focus distance
$19+2.4s$. This creates the slow lateral/dolly parallax in the film. Scene
lengths are uncalibrated; historical metadata names ending in `_m` document an
assumed scale only.

## Original inverse-rendering experiment

The frozen parent scene exposes three continuous parameters:

| parameter | allowed range | role |
|---|---:|---|
| `mist_density` | 0.012–0.060 | base volume density |
| `key_energy` | 3.0–8.0 | key-light energy |
| `water_roughness` | 0.08–0.25 | water material roughness |

The fitter receives a target scene-linear RGB image and searches these bounds
with a 70-render budget. Its objective is a weighted log-domain image loss:

$$
L=0.8\,\operatorname{RMSE}(\log(1+I),\log(1+I^*))_{\mathrm{full}}
 +0.2\,\operatorname{RMSE}(\log(1+I),\log(1+I^*))_{\mathrm{coarse}}.
$$

Acceptance is evaluated separately with raw full-resolution scene-linear RGB
RMSE. A case passes parameter recovery only when every normalized parameter
error is at most 8% of its declared range, and its training and two held-out
render conditions improve over the fixed default by at least 50% RMSE.

The recorded result is mixed: cases A and C pass; case B improves image error
but fails the parameter-accuracy rule. This tests recovery in a known renderer,
not equation discovery, arbitrary-photo reconstruction, or general
identifiability.

## Relationship to ARSENAL fluid models

ARSENAL's spectral-ocean, stable-fluids and shallow-water projects use
source-anchored numerical models with their own bounded validators. They are
the better lane when the question is fluid motion, local interaction or
conservation-oriented diagnostics. TIDELIGHT keeps its four-wave equation
small and visible so the film can show exactly how a scene rule becomes an
image. See the [repository README](../README.md#relationship-to-arsenal) for
the related public work and its limits.
