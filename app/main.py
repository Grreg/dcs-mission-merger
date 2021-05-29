from os.path import expanduser
import os
import logging
import random
import re
import shutil
import tempfile
import zipfile

from slpp import slpp as lua

logging.getLogger().setLevel(logging.DEBUG)

CFG = {
    # This filter the mission files for selection in the Menu. Only Missions
    # containing this filter in their filename will be offered for selection
    # as a BASE Mission but also as selection for merging into Base Mission.
    'miz_name_filter': 'VGAF',

    # Only groups with this name will be copied from the flightlead planning
    # into the base mission. This is required to prevent copying stuff like
    # ground trucks or other not relvant stuff. If you have more flights or
    # a flightlead must plan for a different group as well, it must be added
    # here into the config file - otherwise it will not get copied
    # into the final mission. Groupnames are also tested with added numbers,
    # so in case you write "Stingray", also "Stingray 1", "Stringray 2", 3
    # and 4 are copied as well. So you basically have to configure only the
    # flight names.
    'group_copy_filter': ['Stingray', 'Carver']
    }


class Mission:
    def __init__(self, filepath=None):
        self.cur_unit_id = 1
        self.cur_group_id = 1
        self.mission_data = None
        self.filepath = filepath

        self.used_unit_ids = set()
        self.used_group_ids = set()

        # Keeps track of the used parking position at the start of Mission
        # this is to prevent overlay issues in the mission editor and
        # theoretical game crashes or bugs, altough it seems to be implemented
        # safely by Eagle Dynamics (good job guys!)
        # Structure is: {airdromeId: {usedparkingslot1: unitid; ups2: unitid2}}
        self.parking_map = {}

        # Creates a lookup based on groupnames, collisions are possible should
        # be only used for flightlead filtered groups as they should not
        # collide by definition. Other groups can work, but not guaranteed
        self.groups_blue = {}
        self.group_to_country = {}

        if filepath:
            raw_lua_mission = self.read_mission_from_mizfile(filepath)
            self.mission_data = self.parse_lua_to_missiondata(raw_lua_mission)
            # Directly read and parse the mission to have a consistent cache
            # from the beginning, but parsing is expensive.
            self.initial_parse()

    def initial_parse(self):
        """ To prevent searching multiple times threw the mission data,
        this function iterates over all tree nodes and caching most important
        attributes like all used unitIds, used groupIds or the weather """

        print(f"Initial parse of {os.path.split(self.filepath)[1]}")
        print("-----------------------------------")

        # Find all used group and unit Ids because this is where the merge
        # could most likely collide.
        for cur_coalition, coalition_data in self.mission_data['coalition'].items():
            if not 'country' in coalition_data:
                continue

            for cur_country, country_data in coalition_data['country'].items():
                for unittype in ['vehicle', 'plane', 'static']:
                    if unittype not in country_data:
                        continue

                    for gidx, group in country_data[unittype]['group'].items():
                        
                        # Build lookup for Blue Plane Groupnames for fast
                        # extracting of the planned flight-lead flights
                        if unittype == 'plane' and cur_coalition == 'blue':
                            if group['name'] in self.groups_blue:
                                logging.getLogger().warning(
                                    f"Overwritting lookup for group "
                                    f"{group['name']}. Exists more than once.")
                            self.groups_blue[group['name']] = group
                            self.group_to_country[group['name']] = country_data['name']

                       
                        self.used_group_ids.add(group['groupId'])
                        for uidx, unit in group['units'].items():
                            self.used_unit_ids.add(unit['unitId'])

                        self.safe_parkings(group, self.parking_map)

        print(
            f"Found {len(self.used_group_ids)} groupIds "
            f"and {len(self.used_unit_ids)} unitIds\n")

    def safe_parkings(self, group, parkmap):
        """ This function checks the group for parking positions and safes
        them into a map. This way possible conflicts when adding new units
        can be detected and reported. """


        # Datastructure from the Mission Data
        # 'group' > gid > 'route' > 'points' > 1
        #   ["action"] = "From Parking Area",
        #   ["type"] = "TakeOffParking",
        #   ["airdromeId"] = 23,

        # Abort if we dont have the starting information from this group
        # If the group is on the ground on a parking position
        # the airdrome_id is set, otherwise it will be None
        if not 'route' in group \
                or not 'points' in group['route'] \
                or not 1 in group['route']['points'] \
                or not 'airdromeId' in group['route']['points'][1]:
            return

        airdrome_id = group['route']['points'][1]['airdromeId']

        # retrieve and safe the parking pos for this units
        if airdrome_id:
            if airdrome_id not in parkmap:
                parkmap[airdrome_id] = {}

            for uidx, unit in group['units'].items():
                if 'parking_id' in unit:
                    pid = unit['parking_id']
                    if pid in parkmap[airdrome_id]:
                        other = parkmap[airdrome_id][pid]
                        logging.getLogger().warning(
                            f"Warning: {unit['name']} is on the same parking"
                            f"slot ({pid}) with unit {other['name']}")
                    else:
                        parkmap[airdrome_id][pid] = unit
                        logging.getLogger().debug(
                            f"Parking Position: {unit['name']} "
                            f"-> {airdrome_id}/{pid}")


    def print_wind(self):
        for key in self.mission_data['weather']['wind']:
            speed = self.mission_data['weather']['wind'][key]['speed']
            direction = self.mission_data['weather']['wind'][key]['dir']
            if speed:
                print(f"Wind is {key} from {direction} with {round(speed)}kn")
            else:
                print(f"There is no Wind {key}.")

    def next_id(self, used_set):
        n_id = None
        id_min = 800
        id_max = 999

        for i in range(30):
            n_id = random.randint(id_min, id_max)
            if n_id not in self.used_unit_ids:
                break

        if n_id:
            self.used_unit_ids.add(n_id)
            return n_id

        name = 'unkown'
        if used_set == self.used_unit_ids:
            name = 'unit_id'
        elif used_set == self.used_group_ids:
            name = 'group_id'

        logging.getLogger().error(
            f'Could not find free id for "{name}" between {id_min} and {id_max}')

        return None

    def read_mission_from_mizfile(self, filepath):
        """ Reads the .miz file which contains the whole Mission. As the 
        mission is a ZIP file it will get extracted in memory. UTF-8 is only 
        asumed for mission file encoding. Returns only the RAW data from the
        mission file. No sounds, images, etc. are returned. """
        with zipfile.ZipFile(filepath,"r") as zipobj:
            with zipobj.open('mission') as fh:
                mission_raw = fh.read()
                mission_raw = mission_raw.decode('utf-8')
        return mission_raw

    def save_mission_to_mizfile(self):
        # This function rebuilds the whole zip file over a temp directory
        # which means it costs a lot performance, but there is no supported
        # way to remove or overwrite one file within a ZIP Archive.
        remove_from_zip(self.filepath, 'mission')

        with zipfile.ZipFile(self.filepath, 'a') as zipobj:
            with zipobj.open('mission', 'w') as fh:
                raw_lua_mission = lua.encode(self.mission_data)
                raw_lua_mission = 'mission = \n' + raw_lua_mission
                fh.write(raw_lua_mission.encode('utf-8'))

        print(f"Saved all changes into {self.filepath}.")

    def parse_lua_to_missiondata(self, raw_lua_mission):
        """ The mission is originally saved in a lua format, but to manipulate the
        data in a consistent way, without messing around with regexes, its required
        to parse the lua data into python data types. """
        # Remove the inital variable assignment, as we only need
        # the data and not the lua variable name
        raw_lua_mission = raw_lua_mission.replace('mission = ', '')
        # This function translates the lua text file into python datatypes
        mission_data = lua.decode(raw_lua_mission)
        return mission_data

    def add_group(self, group_data, coalition="blue", country="Germany"):
        """ Adding a group implies also verification for possible conflicts
        and solving them in a best possible way. Conflicts can be, but are not
        limited to, same group names, same group ids, same unit ids, same pilot
        names, same parking positions, etc. Errors are hard to detect as the
        mission simply does not start and crash the server, therefore work 
        here carefully and test your final missions before running them. 
        Currently also all flights are added into the blue coalition. """

        if group_data['name'] in self.groups_blue:
            print(f"Group {group_data['name']} already exists in Mission!"
                  f" Import skipped!")
            return

        # Get the next available group id and set it
        gid = self.next_id(self.used_group_ids)
        group_data['groupId'] = gid

        # Iterate over all UnitIds and update them as well
        # TODO: update unit ids
        for uidx, unit in group_data['units'].items():
            if unit['unitId'] not in self.used_unit_ids:
                self.used_unit_ids.add(unit['unitId'])
                continue
            
            # Create and set new Id on collision
            new_id = self.next_id(self.used_unit_ids)
            unit['unitId'] = new_id
            self.used_unit_ids.add(unit['unitId'])
            print(f"Unit {unit['name']} got new id: {new_id}, due to conflicting ids.")

            # Rudimentary verification for parking slots without solving them
            # as currently are airports share the same parking id slots, which
            # is not correct, but easy to implement for the start.
            if 'parking_id' in unit:
                if unit['parking_id'] in self.used_parking_ids:
                    print(
                        f"Warning: Verify parking position for {unit['name']}."
                        f" Detected possible conflict. Automatic solving not "
                        f" implemented yet.")
                else:
                    self.used_parking_ids.add(unit['parking_id'])

        # DataPath
        # mission_data > 'coalition' > coalition > 'country' > clistid > 'plane'
        # > 'group' > glistid > GROUP_DATA_HERE :D
        country_idx = get_idx_by_subkey(
            self.mission_data['coalition'][coalition]['country'],
            'name', country)

        germanys_plane_groups = \
            self.mission_data['coalition'][coalition]['country'][country_idx]\
                ['plane']['group']
        
        idx = get_next_idx(germanys_plane_groups)
        germanys_plane_groups[idx] = group_data

        # Write the group index to have a quicklookup on this group and
        # prevent double entries
        self.groups_blue[group_data['name']] = germanys_plane_groups[idx]
        # print(f"Added {group_data['name']} into groups_blue")

        print(
            f'Added group {group_data["name"]} '
            f'with new groupid {group_data["groupId"]} '
            f'at index {idx} '
            f'into country idx {country_idx} ({country})')
      
        return gid


def get_idx_by_subkey(tree, subkeyname, value):
    """ Due to the datastructure also lists are dictionaries accessible by
    their id. But sometimes you need to find the right item by the name
    which is saved inside this object. For example if you need the Country
    "Germany" or a certain flight. This function can be handy to get this
    done fast, e.g. get_idx_by_subkey(
        self.mission_data['coalition'][coalition]['country']),
        'name', 'Germany')
    """
    for idx, obj in tree.items():
        if not subkeyname in obj:
            continue
        if not obj[subkeyname] == value:
            continue
        return idx

def get_next_idx(dictlist):
    cur_idx = 1
    for idx, obj in dictlist.items():
        cur_idx = max(cur_idx, idx+1)
    return cur_idx


def remove_from_zip(zipfname, *filenames):
    """ Stackoverflow Magic as you cant simply edit a file in a zip file
    https://stackoverflow.com/questions/4653768/overwriting-file-in-ziparchive
    """
    tempdir = tempfile.mkdtemp()
    try:
        tempname = os.path.join(tempdir, 'new.zip')
        with zipfile.ZipFile(zipfname, 'r') as zipread:
            with zipfile.ZipFile(tempname, 'w') as zipwrite:
                for item in zipread.infolist():
                    if item.filename not in filenames:
                        data = zipread.read(item.filename)
                        zipwrite.writestr(item, data)
        shutil.move(tempname, zipfname)
    finally:
        shutil.rmtree(tempdir)


def select_base_mission_cmdline(options):
    print("\n1. Choose BASE MISSION")
    print("----------------------")
    print(f"""
        This file will *never* be overwritten! Its basically the whole
        Mission without the Player Flights as they have to design their
        own strategy. (only files with {CFG['miz_name_filter']} in their
        file name are shown to prevent a long selection list)
        
        """)

    for idx, (path, filename) in enumerate(options):
        print(f"[{idx}] {filename}")

    selection = int(input("\n    Choose the Base Mission: "))

    mission_base = os.path.join(options[selection][0], options[selection][1])
    logging.getLogger().debug(mission_base)
    return mission_base


def select_flights_cmdline(options):
    missions = []
    print("\n2. Choose FLIGHT-PLANS")
    print("----------------------")
    print("""
        Select all Missions provided by the Flightleads where they saved their
        airplanes, loadouts and waypoints. These will be merged into a new
        final mission for the server. Use comma "," to separate the selections,
        e.g.: 1,3,4
        """)

    for idx, (path, filename) in enumerate(options):
        print(f"[{idx}] {filename}")

    selection = input("\n    Choose Flight-Plans: ")
    selection = re.split(r',\s*', selection)
    for val in selection:
        missions.append(
            os.path.join(options[int(val)][0], options[int(val)][1]))

    return missions


def main():
    # Find the Home directory for the current user,
    # because DCS Mission data is saved there.
    home = expanduser("~")
    missionsfolder = os.path.join(home, 'Saved Games', 'DCS', 'Missions')

    # Find DCS Folder and read available Mission files
    options = []
    for filename in os.listdir(missionsfolder):
        if filename.endswith(".miz") and CFG['miz_name_filter'] in filename:
            # print(filename)
            options.append((missionsfolder, filename))

    # Offer selection for the Mission BASE with all Enemy strategies, etc.
    mission_base = select_base_mission_cmdline(options)
    # mission_file_name = 'Caucasus_VGAF_Campaign_01_v03_Base.miz'
    # mission_base = os.path.join(missionsfolder, mission_file_name)
    print()

    # Offer multiple selection for flight plans
    missionlist_flights = select_flights_cmdline(options)
    print()


    # Create a new file for the merged Version
    # mission_tmp_file = mission_file_name.replace('.miz', '_temp.miz')
    mission_tmp_file = 'VGAF_Campaign_02_sharkbite.miz'
    mission_temp = os.path.join(missionsfolder, mission_tmp_file)
    shutil.copyfile(mission_base, mission_temp)
    logging.getLogger().debug('Created temp mission file based on a copy')

    # Parses the generated TEMP file from the Mission Base - as this is only
    # the temp file, this data can be also saved backed into the file.
    final_mission = Mission(mission_temp)

    # Read the Flights-Plannings and copy them into the current mission
    # example_flight_file_names = ['Caucasus_VGAF_Campaign_01_v03_stingray.miz']
    for mission_file in missionlist_flights:
        # mission_file = os.path.join(missionsfolder, flight_mission)

        my_mission = Mission(mission_file)

        for gname in CFG['group_copy_filter']:
            for appendix in ['', ' 1', ' 2', ' 3', ' 4', '-1', '-2']:
                if gname+appendix in my_mission.groups_blue:
                    final_mission.add_group(
                        my_mission.groups_blue[gname+appendix],
                        country=my_mission.group_to_country[gname+appendix])
    
    print(f"Post processing steps")
    print(f"---------------------")
    final_mission.save_mission_to_mizfile()

    print(f"")
    exit()


if __name__ == '__main__':
    main()
