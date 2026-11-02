# Quantum error correction, in plain words

This lab runs classical CPU simulations. It does not run a quantum computer. The NumPy part tracks binary errors; Stim efficiently tracks Clifford circuits and Pauli noise. Neither model includes every effect in hardware.

## From physical qubits to a logical qubit

A **physical qubit** is one device, such as an ion or superconducting circuit. A **logical qubit** is information encoded across several physical qubits so some errors can be detected and corrected. Redundancy costs qubits, measurements, time, and classical decoding. It is not copying an unknown quantum state into independent backups: the encoded state is shared across the devices.

A **bit flip**, written X, exchanges 0 and 1. A **phase flip**, written Z, changes the relative sign in a superposition: `(0 + 1)/sqrt(2)` becomes `(0 - 1)/sqrt(2)`. Measuring those two states in the 0/1 basis gives the same probabilities. A Y error combines bit and phase changes, up to an irrelevant overall phase. Protecting only against X errors is therefore not full quantum error correction.

## Stabilizers and syndromes: ask about agreement

A **stabilizer** is a check that has a predictable value on a valid encoded state. Measuring a check should reveal evidence of errors without revealing the unknown logical state. A collection of check outcomes is the **syndrome**.

For a three-qubit repetition encoding, logical 0 is `000` and logical 1 is `111`. The checks compare neighboring bits: `Z0 Z1` and `Z1 Z2`. In binary form the syndrome is `[b0 XOR b1, b1 XOR b2]`. We record agreement as 0 and disagreement as 1; these correspond to stabilizer eigenvalues +1 and -1.

Worked example: an X on the middle qubit changes `000` to `010`. Its syndrome is `[1, 1]`. An X on the left gives `100` and syndrome `[1, 0]`. Both `000` and `111` have syndrome `[0, 0]`, so the checks do not reveal which logical value was stored. This ambiguity is useful for privacy of the logical state, but it also makes undetected logical errors possible.

## Repetition code and distance

For odd **distance** d, repeat the bit d times. A majority vote recovers a stored classical bit if fewer than half the bits flipped. A syndrome lookup decoder instead selects a minimum-weight error pattern compatible with the syndrome and applies that correction. “Weight” here means number of flipped bits, not a probability learned by a neural network.

Example: with d=3, `110` has syndrome `[0, 1]`. The same syndrome comes from the one-error pattern `001`. The minimum-weight decoder chooses `001`, leaving `111`: a logical failure. It cannot tell that two flips actually occurred. At d=5, two flips are still correctable. In general an odd-distance code corrects up to `(d-1)/2` errors in its protected channel.

The NumPy majority experiment measures a prepared classical memory; reading every data bit would destroy a general quantum superposition. The syndrome decoder illustrates the correction rule without that claim. This repetition encoding has X-error distance d but an unprotected phase-error channel: a single Z can act logically. Calling it a distance-d **quantum code against arbitrary errors** would be misleading.

For independent bit-flip probability p and perfect checks, majority failure is the binomial tail: sum `choose(d,k) p^k (1-p)^(d-k)` for k greater than d/2. For d=3, this is `3p² - 2p³`. At p=0.1 it is 0.028, compared with 0.1 for an unencoded bit. At p=0.5 both are 0.5. This ideal repetition break-even is not a surface-code hardware threshold.

## Surface code: a two-dimensional patch

The surface code places data qubits on a two-dimensional layout with local X-type and Z-type checks, measured using additional syndrome qubits. It can detect both bit and phase errors. Error strings create check violations at their ends; a string crossing the patch in the wrong way can change a logical value without leaving a detectable endpoint. The shortest such logical string defines the **code distance**.

A rotated patch uses `d²` data qubits and approximately `d²-1` check qubits: `2d²-1` physical qubits per logical memory patch. At d=3, that is 9 data plus 8 check qubits, or 17. This count excludes routing, spare qubits, control hardware, and gates between logical patches.

## Decoding and minimum-weight perfect matching

The decoder sees check changes, not the hidden errors. In repeated measurements, a **detection event** says a check changed relative to its expected value in space and time. A data error can make nearby spatial checks disagree; a measurement error can make the same check disagree in adjacent rounds.

**Minimum-weight perfect matching (MWPM)** connects detection events to each other or to suitable boundaries. Edges represent candidate error paths. Less likely paths receive larger weights, often based on log odds. “Perfect” means all required endpoints are accounted for, not that the correction is always correct. Degeneracy, correlated faults, and a wrong noise model can make a minimum-weight correction fail. Stim provides a detector error model; PyMatching builds and solves this graph. Decomposing multi-detector faults into graphlike pieces is an approximation for some correlations.

The ML experiment asks a simpler supervised question: given the detector bits, did the logical observable flip? A small MLP predicts that bit; it does not reconstruct a quantum state. Its test shots are separate from training and validation shots. We compare all decoders on the same test shots, including a training-only empirical syndrome lookup table.

## Logical error rates, thresholds, and uncertainty

A **logical error rate** is failures divided by trials, with the trial stated clearly. This lab reports failure per complete memory experiment. Surface-code experiments use d rounds, so different distances also have different experiment lengths. A separately labelled per-round proxy divides the experiment failure rate by its round count; it is only a small-error approximation.

Example: 12 logical failures in 10,000 independent shots gives 0.0012 per experiment. A confidence interval describes sampling uncertainty; zero failures does not prove zero risk. The lab uses 95% Wilson intervals for proportions and a seeded binomial bootstrap for curve crossings and scaling fits.

An **error threshold** is an asymptotic property: below it, increasing a code family’s distance can suppress logical errors under specified assumptions. Crossings of d=3,5,7 curves are only finite-size estimates, not proof of that limit. This lab searches only the predeclared sweep interval, reports each distance-pair crossing, and reports when bootstrap samples have no crossing. Its confidence intervals do not include noise-model or finite-size bias. Literature values around 0.5–1% depend on the circuit, decoder, and noise convention; a different measured crossing is a result to explain, not a reason to adjust the sweep afterward.

## Fault tolerance and why measurement errors matter

**Fault tolerant** means the procedures themselves keep a small number of physical faults from turning into an uncorrectable logical fault. A code alone is not enough: checks, resets, gates, readout, scheduling, and classical processing can fail. A faulty check can otherwise spread errors or trigger the wrong correction.

With one noisy check round, `[1,1]` might indicate a middle-qubit data error—or two bad check readings. Several rounds provide time history to distinguish these explanations. The NumPy phenomenological model adds data flips each round and noisy check outcomes, then a perfect final data readout; a readable maximum-likelihood **Viterbi** decoder uses the whole history. Stim's circuit-level model places faults after gates and around reset/readout, including propagation through the check circuit. These are different experiments and should not share an unlabeled threshold claim.

The resource calculation extrapolates a fitted suppression law to much smaller error targets than directly observed. That is a planning illustration, not a validated hardware design or a real fault-tolerant compiler. Every number must retain its noise model, trial definition, distance range, shot count, and uncertainty.

## Short glossary

- **Physical / logical qubit:** a device / encoded quantum information.
- **X / Z / Y:** bit flip / phase flip / their combination.
- **Stabilizer / syndrome:** a parity-like check / the collected check results.
- **Detection event:** an unexpected check parity, often a change between rounds.
- **Distance / weight:** smallest logical error's size / an error pattern's size.
- **Decoder / MWPM:** inferred correction / graph matching of detection endpoints.
- **Code capacity / phenomenological / circuit level:** perfect checks / noisy abstract checks / faults in the check circuit itself.
- **Logical error rate / threshold:** observed encoded failure frequency / a model-dependent asymptotic change in distance scaling.
- **Shot / confidence interval:** one simulation trial / sampling uncertainty about its rate.
- **Fault tolerance:** error containment by the entire procedure, not just an encoding.

References: [Stim's circuit format](https://github.com/quantumlib/Stim/blob/main/doc/file_format_stim_circuit.md), [PyMatching documentation](https://pymatching.readthedocs.io/en/stable/), and [Stephens, *Fault-tolerant thresholds for quantum error correction with the surface code*](https://arxiv.org/abs/1311.5003). The latter reports model-dependent circuit thresholds spanning approximately 0.5–1.14%; it is a comparison, not an expected value for this lab.
