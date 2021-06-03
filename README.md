What can you do with this?
==========================
Our situation: We have a mission builder who was originally building everything
from enemy forces up to the flight plans for each flight. This led to less
tactical ownership for the flights and to some excuses "if we would have planned
it different we would have successfully acclompished the mission" :D

Solution: 
* Mission builder now only builds the enemy forces 
    and creates the NPC environment
* The important informations and goals are shared with all flights,
    like "destroy the bridge,   expect heavy hostile SAMs and possible air units, secondary goal is ..."
* Each flight plans his own waypoints, loadouts and strategy for the mission.
    This is directly build in the Mission Editor and saved as a mission and send
    to the mission builder
* The mission builder runs this merge script which copies all planned flights
    into the final mission (new file to prevent any issues!)

Pros:
    * Flights get Ownership for their strategy
    * More responsibilites and more fun
    * No excuses for poorly planned missions :D
    * Distributes Workload on more people

Cons:
    * Inter-Flight adjustments are more complicated, when will each flight be where?
        this requires additional communication, but can enforce better collaboration
        and team-building
    * Maybe a bit less realistic as Flight leads probably dont have full responsibility
        for this planning.

Current state of work
=====================
It works ... but well, its kinda hacky here and there. For example the filter
for missions shown is hardcoded and not in a yaml config file. Will do that soon :D
Also there is only support for merging planes, no other units are supported.

How to use
==========
* Python 3.9 recomennded, (probably runs with 3.6+)
* Adjust the Mission Filename-filter in the source files to see only Campaign missions
* Run the script
* Select the BASE Mission (its the environment with all enemy units, weather, etc.)
* Select the Flight Missions (only planes are copied, but including loadout, radio settings, etc.)
* Check for warnings (sometimes planes were placed on the same parking position, this must be fixed manually via the mission editor)
* Test the final mission
* Have fun!

Known Issues
============

Parking positions cant be automatically resolved
------------------------------------------------
In the Mission Editor it is not possible to place to units on the same parking
position. Although this can happen by the automatic merge of this script.
Because there is a for me unkown mapping between 'parking_id' and 'parking' it
is currently not possible to automatically resolve this. But you we get a
warning from the merge tool, to resolve it.

Solution: 
    Altough its possible that the game still works and automatically
    resolves this. It is recommended to go into the Mission Editor of the final
    merged map and change the position there for the affected units. Or change
    the conflicting positions in the Missions from the Flightleads.