# Zynthian User Interface

> **This is the FreeMixer fork** of [zynthian/zynthian-ui](https://github.com/zynthian/zynthian-ui), branch `vangelis`.
> It adds an engine, `PH`, that runs a chain's LV2 and CLAP plugins through
> [plugin-hostd](https://github.com/FreeMixer/plugin-hostd): the plugins of a chain that run in series in one worker process, a plugin qualified as not
> real-time safe in a worker of its own, and a lost worker restarted; what a crash does through this engine is still to be measured. JACK stays as it is, and jalv stays
> for what plugin-hostd refuses. Plugin menus are ordered from the measurements of
> [plugin-qualify](https://github.com/FreeMixer/plugin-qualify), every plugin has a Factory and a User preset bank, and
> controller pages follow the plugin's own sections. Its tests run in CI on every change.
>
> On this fork the engine is the default; in the series offered upstream it stays off until a user sets it, and
> setting `ZYNTHIAN_PLUGIN_ENGINE=jalv` goes back. Whether plugins share a worker is plugin-hostd's `grouping`
> setting in `/zynthian/config/plugin-hostd.conf`: with `grouping off` each plugin runs in a worker of its own, and
> `grouping on` lets the daemon plan which neighbours in series share one. How to install and use it, the measurements and where it stands:
> <https://openmixer.org/docs/zynthian>.
> The changes are prepared for upstream as a series on upstream's `tomita`, one PR per step, each branch the one
> before it plus one change: `upstream-series-t20261126/02..10` here and `upstream-series-t20261126b/01..04` on the
> companion fork, [FreeMixer/zynthian-sys](https://github.com/FreeMixer/zynthian-sys), whose settings keep the
> stock values (`ZYNTHIAN_PLUGIN_ENGINE=jalv`, mod-host by `jack_load`). None of it is posted upstream yet. On a
> Raspberry Pi 5 the series loads a snapshot of three LV2 instruments through jalv with the stock setting and
> through plugin-hostd with `ZYNTHIAN_PLUGIN_ENGINE=plugin-hostd`, and the zynthian journal shows no error that this
> fork's own run does not show (2026-11-27). Install the daemon and the packages from the
> [FreeMixer channel](https://www.openmixer.org).
>
> PRs merge into `openmixer`, not the default branch: close the issue by hand at merge.

The text below is Zynthian's own.

[Zynthian](http://zynthian.org) is an Open Synth Platform based on Raspberry Pi, Linux and Free Software Synthesizers.

The [ZynthianOS SD-image](https://os.zynthian.org/zynthianos-last-stable.zip) has all the software you need for building a ZynthianBox, including a good amount of sound libraries and presets.

This repository contains the software for the Engine Manager & User Interface.

![Image of Zynthian Box Design](https://wiki.zynthian.org/images/e/ed/Zynthian_v5_render_desplegado.jpg)

You can learn more about the Zynthian Project in any of our sites: 

+ [website](https://zynthian.org)
+ [wiki](https://wiki.zynthian.org)
+ [user's guide](https://help.zynthian.org)
+ [blog](https://blog.zynthian.org)
+ [forum](https://discourse.zynthian.org) => Join the conversation!!

You can buy official kits in the zynthian shop:

+ [shop](https://shop.zynthian.org)
