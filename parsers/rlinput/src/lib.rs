//! Input reconstruction support crate.
//!
//! S1.0 intentionally contains no estimator logic; it only proves the crate
//! layout and optional RocketSim integration compile.

#[cfg(feature = "sim")]
pub mod sim;
