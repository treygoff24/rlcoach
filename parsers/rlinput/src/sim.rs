//! Optional RocketSim wiring.

/// Pinned RocketSim Rust wrapper used by the S1 discovery spike.
pub const ROCKETSIM_RS_VERSION: &str = "0.37.0";

#[cfg(test)]
mod tests {
    use rocketsim_rs::{
        math::{RotMat, Vec3},
        sim::{Arena, ArenaConfig, CarConfig, CarControls, CarState, GameMode, Team},
    };

    #[test]
    fn rocketsim_void_arena_steps_full_car_state() {
        rocketsim_rs::init_from_mem(&[], &[]);

        let mut arena = Arena::new(GameMode::TheVoid, ArenaConfig::default(), 120);
        assert!((arena.get_tick_rate() - 120.0).abs() < 0.001);

        let car_id = arena.pin_mut().add_car(Team::Blue, CarConfig::octane());
        let car_state = CarState {
            pos: Vec3::new(100.0, -250.0, 300.0),
            rot_mat: RotMat::new(Vec3::Y, Vec3::new(-1.0, 0.0, 0.0), Vec3::Z),
            vel: Vec3::new(400.0, 50.0, 25.0),
            ang_vel: Vec3::new(0.1, -0.2, 0.3),
            boost: 80.0,
            is_on_ground: false,
            wheels_with_contact: [false; 4],
            ..CarState::default()
        };

        arena
            .pin_mut()
            .set_car(car_id, car_state)
            .expect("car id from add_car should be settable");
        arena
            .pin_mut()
            .set_car_controls(
                car_id,
                CarControls {
                    throttle: 1.0,
                    steer: 0.25,
                    pitch: -0.4,
                    yaw: 0.3,
                    roll: -0.2,
                    jump: false,
                    boost: true,
                    handbrake: true,
                },
            )
            .expect("car id from add_car should accept controls");

        for _ in 0..8 {
            arena.pin_mut().step(1);
        }

        let updated = arena.pin_mut().get_car(car_id);
        assert_eq!(arena.get_tick_count(), 8);
        assert!(updated.pos.x.is_finite());
        assert!(updated.pos.y.is_finite());
        assert!(updated.pos.z.is_finite());
        assert!(updated.boost < 80.0);
        assert_eq!(updated.last_controls.throttle, 1.0);
        assert!(updated.last_controls.boost);
    }
}
