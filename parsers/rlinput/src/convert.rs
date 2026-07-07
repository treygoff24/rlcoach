use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct ReplayVec3 {
    pub x: f32,
    pub y: f32,
    pub z: f32,
}

pub type RotationMatrix = [[f32; 3]; 3];

pub fn replay_units_to_rocketsim(value: ReplayVec3) -> ReplayVec3 {
    value
}

pub fn rocketsim_units_to_replay(value: ReplayVec3) -> ReplayVec3 {
    value
}

pub fn replay_quat_xyzw_to_rot_mat(quat_xyzw: [f32; 4]) -> RotationMatrix {
    let [mut x, mut y, mut z, mut w] = quat_xyzw;
    let norm = (x * x + y * y + z * z + w * w).sqrt();
    if norm == 0.0 {
        return identity_rot_mat();
    }
    x /= norm;
    y /= norm;
    z /= norm;
    w /= norm;

    [
        [
            1.0 - 2.0 * (y * y + z * z),
            2.0 * (x * y - z * w),
            2.0 * (x * z + y * w),
        ],
        [
            2.0 * (x * y + z * w),
            1.0 - 2.0 * (x * x + z * z),
            2.0 * (y * z - x * w),
        ],
        [
            2.0 * (x * z - y * w),
            2.0 * (y * z + x * w),
            1.0 - 2.0 * (x * x + y * y),
        ],
    ]
}

pub fn identity_rot_mat() -> RotationMatrix {
    [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
}

#[cfg(test)]
mod tests {
    use super::*;

    const EPS: f32 = 1e-5;

    fn assert_matrix_close(actual: RotationMatrix, expected: RotationMatrix) {
        for row in 0..3 {
            for col in 0..3 {
                assert!(
                    (actual[row][col] - expected[row][col]).abs() < EPS,
                    "matrix[{row}][{col}] expected {}, got {}",
                    expected[row][col],
                    actual[row][col]
                );
            }
        }
    }

    fn quat_axis_angle(axis: [f32; 3], radians: f32) -> [f32; 4] {
        let half = radians / 2.0;
        let s = half.sin();
        [axis[0] * s, axis[1] * s, axis[2] * s, half.cos()]
    }

    fn quat_mul(a: [f32; 4], b: [f32; 4]) -> [f32; 4] {
        let [ax, ay, az, aw] = a;
        let [bx, by, bz, bw] = b;
        [
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        ]
    }

    #[test]
    fn identity_quaternion_is_identity_matrix() {
        assert_matrix_close(
            replay_quat_xyzw_to_rot_mat([0.0, 0.0, 0.0, 1.0]),
            identity_rot_mat(),
        );
    }

    #[test]
    fn ninety_degree_axis_rotations_are_pinned() {
        let qx = quat_axis_angle([1.0, 0.0, 0.0], std::f32::consts::FRAC_PI_2);
        let qy = quat_axis_angle([0.0, 1.0, 0.0], std::f32::consts::FRAC_PI_2);
        let qz = quat_axis_angle([0.0, 0.0, 1.0], std::f32::consts::FRAC_PI_2);

        assert_matrix_close(
            replay_quat_xyzw_to_rot_mat(qx),
            [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]],
        );
        assert_matrix_close(
            replay_quat_xyzw_to_rot_mat(qy),
            [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]],
        );
        assert_matrix_close(
            replay_quat_xyzw_to_rot_mat(qz),
            [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        );
    }

    #[test]
    fn composed_rotation_is_pinned() {
        let qz = quat_axis_angle([0.0, 0.0, 1.0], std::f32::consts::FRAC_PI_2);
        let qx = quat_axis_angle([1.0, 0.0, 0.0], std::f32::consts::FRAC_PI_2);
        let composed = quat_mul(qz, qx);

        assert_matrix_close(
            replay_quat_xyzw_to_rot_mat(composed),
            [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        );
    }

    #[test]
    fn replay_and_rocketsim_units_pass_through() {
        let value = ReplayVec3 {
            x: 1.0,
            y: -2.0,
            z: 3.5,
        };
        assert_eq!(replay_units_to_rocketsim(value), value);
        assert_eq!(rocketsim_units_to_replay(value), value);
    }
}
