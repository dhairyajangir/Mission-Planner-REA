# Copter sensor setup views in the original release

Two disposable Ubuntu-E guests ran the Mission Planner 1.3.83 release under Mono's interpreter on a private X display, connected to the pinned Copter simulator through loopback TCP. The [existing launcher](../gui-original-copter-peripheral-views/observe-interpreted.py) starts a fresh extraction and temporary user profile each time. Neither guest had a physical peripheral. The window title identified ArduCopter V4.8.0-dev (15a10bb4). All page selections used the SETUP sidebar.

## Optional Hardware, Range Finder and Optical Flow

Run `sensors-5YmAGZtg` opened Optional Hardware before selecting either sensor. Its optional-equipment instructions rendered with both Range Finder and Optical Flow listed in the sidebar. The Range Finder page displayed a sensor-type selector set to None, Distance 0 and Voltage 0. Optical Flow displayed None, two zero scaling values, another zero-valued numeric control, and three sensor offsets of 0.000 metres forward, right and down. These are on-screen values in this simulator profile. [Optional Hardware](optional.png) · [Range Finder](rangefinder.png) · [Optical Flow](optical-flow.png)

## ADSB

In run `sensors-HXgw6hfd`, SETUP → Mandatory Hardware → ADSB logged `ConfigADSB` and completion of its activation handler. The X window tree then contained Flight Identification, Aircraft Registration and the ADSB_TYPE control. The screen still showed a blank pane with Mandatory Hardware highlighted. A later click on Optional Hardware never produced its activation-log entry. This run establishes control construction. Visible ADSB setup fields and a completed Optional Hardware transition were absent from these captures. The 1,431-parameter readback reported ADSB_TYPE, FLOW_TYPE and RNGFND1_TYPE all zero. All 657 recorded Copter heartbeats were disarmed. [Initial screen](sensors-HXgw6hfd/adsb.png) · [Later screen](sensors-HXgw6hfd/adsb-settled.png) · [Later tree](sensors-HXgw6hfd/windows-adsb-settled.txt) · [Application log](sensors-HXgw6hfd/release.log)

The second guest repeated the ADSB selection after both optional sensor views had rendered. Once again the application logged `ConfigADSB`, and the later tree contained the identification fields and ADSB_TYPE control. Both screenshots retained the blank pane. In the earlier modified Windows sweep, the page visibly displayed Flight Identification and Aircraft Registration. The separate component harness reported successful activation for all three sensor pages. [Second ADSB capture](adsb.png) · [Later capture](adsb-settled.png) · [Later tree](windows-adsb-settled.txt) · [Modified Windows observations](../coverage/copter-menu-capture-review.csv) · [Component results](../sitl-evidence/page-state/page-state.csv)

The setup source registers ADSB under Mandatory Hardware. Range Finder and Optical Flow have distinct optional-page registrations. Each requires its display setting, a connected vehicle and a complete parameter list. The separate PX4Flow entry opens a different component. [ADSB registration](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L263) · [Optional sensor registrations](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L287)

## Telemetry and release identity

The second guest reported the same 1,431-parameter count and the same three zero sensor-type values as the first. Its 501 Copter heartbeats all indicated disarmed. In each of the six-second windows starting at the Optional Hardware, Range Finder and Optical Flow clicks, the telemetry file recorded six outgoing ground-station heartbeats. Each ADSB click coincided with six heartbeats and one time-synchronization message. Across both complete logs, common background traffic included stream requests, message requests and time synchronization. The outgoing message inventory contained zero PARAM_SET or PARAM_EXT_SET messages. Neither session included a calibration or a sensor measurement with a physical device. [Decoded traffic and parameter values](verification.json)

All 1,317 release files matched the original archive after each session. [First archive check](sensors-HXgw6hfd/archive-comparison.json) · [Second archive check](archive-comparison.json)

## Replay

From the repository root, run `python gui-original-copter-sensor-options/verify.py --check` to replay the archive, UI and telemetry evidence. For a fresh session use a separate copy of the recorder and `python3 gui-original-copter-peripheral-views/observe-interpreted.py` in the prepared Ubuntu-E environment. The printed run ID identifies the independent guest. Use `python3 gui-original-copter-sensor-options/observe.py RUN_ID startup 0` to inspect startup. Each subsequent invocation takes a label, the next action number and the two coordinates of a visible navigation target. Finish with `finish NEXT_ACTION`. The recorder writes into its own directory.
