"""
@example: manufacturing system simulation
@author: VD

"""

import heapq
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np


# ============================================================
# EVENT CLASS
# ============================================================

class Event(object):
    """Class representing an event in the simulation"""
    JOB_ARRIVAL = 0
    ASSEMBLY_COMPLETE = 1
    TRANSPORT_COMPLETE = 2
    REPLENISHMENT_COMPLETE = 3

    EVENT_TO_STR = {
        0: "JOB_ARRIVAL",
        1: "ASSEMBLY_COMPLETE",
        2: "TRANSPORT_COMPLETE",
        3: "REPLENISHMENT_COMPLETE"
    }

    def __init__(self, event_type, time, job, resource=None, location=None):
        self.event_type = event_type
        self.time = time
        self.job = job
        self.resource = resource
        self.location = location

    def __lt__(self, other):
        """Less than method determines how a list or heapq of Event classes will be sorted"""
        if self.time == other.time:
            if self.job is None:
                return False
            return self.job.id < other.job.id
        return self.time < other.time

    def __str__(self) -> str:
        """String method determines how an Event class will be printed"""
        resource_info = f" on Resource {self.resource.id}" if self.resource is not None else ""
        return f"Event {self.EVENT_TO_STR[self.event_type]} for Job {self.job.id if self.job is not None else None}{resource_info} at time {self.time:.2f}" 


# ============================================================
# RESOURCE (WORKSTATIONS, AGVS & AMRS)
# ============================================================

class Resource(object):

    def __init__(self, type, resource_id, capacity, location, refill_level, max_trolley_spots):
        """Class representing a resource in the simulation"""
        self.id = resource_id
        self.type = type
        self.capacity = capacity
        self.location = location
        self.queue = []
        self.current_entities = []
        self.blocked_entities = []   # jobs done processing, waiting for AGV pickup
        self.is_busy = False
        self.replenishment_level = refill_level
        self.trolley_spots = max_trolley_spots
        self.resources = max_trolley_spots
        self.available_time = 0

    def seize(self, job):
        """Assign a job to this resource and seize the resource"""
        self.current_entities.append(job)
        self.is_busy = True

    def release(self, job_id):
        """Release a specific job from the resource"""
        self.current_entities = [e for e in self.current_entities if e.id != job_id]
        self.is_busy = len(self.current_entities) > 0

    def is_available(self):
        """Check if resource is available to process a job"""
        return len(self.current_entities) < self.capacity


# ============================================================
# JOB
# ============================================================

class Job(object):
    """Class representing a job in the simulation"""
    def __init__(self, job_id, job_type, route, proc_times):
        self.id = job_id
        self.type = job_type
        self.route = route
        self.proc_times = proc_times

        self.current_op = 0
        self.current_location = 00

        self.arrival_time = None
        self.departure_time = None
        self.start_time = None
        self.resource_id = None

        self.total_replenishment_wait = 0            # cumulative wait in replenishment queue
        self.total_transport_wait = 0     # cumulative wait in transport queue
        self.ws_entry_time = None         # timestamp when job entered current ws
        self.ws_blocked_time = None       #cumulative time that the job was blocked 
        self.transport_entry_time = None  # timestamp when job entered transport queue
        self.replenishment_entry_time = None  # timestamp when job entered transport queue


    def remaining_ops(self):
        return len(self.route) - self.current_op

    # def current_pt(self):
        
        
        
        
    #     return self.resource_id


# ============================================================
# SIMULATION
# ============================================================

class Simulation(object):

    def __init__(self, machines_config, n_agvs, n_amrs, agv_rule, amr_rule):
        self.now = 0
        self.events = []

        # Capacity of ws = the number of machines in ws
        self.workstations = [Resource("Workstation", i, 1, machines_config[i][0], machines_config[i][1], machines_config[i][2]) for i in machines_config.keys()]
        self.waiting_prep_station = []
        # Cap = 1, all AGVs is located at the depot initially
        self.agvs = [Resource("AGV", i + 1, 1, 90, None, None) for i in range(n_agvs)]
        self.transport_queue = []

        self.amrs = [Resource("AMR", i + 1, 1, 100, None, None) for i in range(n_amrs)]
        self.replenishment_queue = []

        self.agv_rule = agv_rule
        self.amr_rule = amr_rule

        self.waiting_prep_station = []
        self.blocked_W10 = []
        self.blocked_W20 = []
        self.blocked_W30 = []
        self.blocked_W40 = []
        self.blocked_W50 = []
        self.blocked_W60 = []



        # # distance matrix
        # self.distance = np.array([
        #     [0,150,213,336,300,150],
        #     [150,0,150,300,336,213],
        #     [213,150,0,150,213,150],
        #     [336,300,150,0,150,213],
        #     [300,336,213,150,0,150],
        #     [150,213,150,213,150,0]
        # ])

        # self.speed = 5  # ft/sec

        # ---- statistics ----
        self.completed_jobs = []
        self.job_counter = 0
        self.replenishment_counter = 0
        self.blocked_times_ws = []
        self.waiting_times_agvs = []

        self.last_event_time = 0
        self.collecting = False

        self.area_queue   = [0]*len(machines_config)
        self.max_queue    = [0]*len(machines_config)
        self.area_busy    = [0]*len(machines_config)
        self.area_blocked = [0]*len(machines_config)

        self.area_system = 0
        self.agv_loaded_time = 0
        self.agv_empty_time = 0
        self.amr_empty_time = 0
        self.amr_loaded_time = 0
        self.area_transport_queue = 0
        self.max_transport_queue  = 0

    # ============================================================
    # RANDOM GENERATION
    # ============================================================

    def get_inter_arrival_time(self):
        """Return the inter-arrival time with respect to a specific distribution"""
        return np.random.exponential(300)

    def generate_job(self):
        """Gerenate job arrivals to the system"""
        # p = random.random()

        # if p < 0.3:
        #     return Job(self.job_counter, 1,
        #                   [3,1,2,5,6], # route includes depot (6) as final destination; proc_times only covers actual operations
        #                   [0.25,0.15,0.10,0.30])
        # elif p < 0.8:
        #     return Job(self.job_counter, 2,
        #                   [4,1,3,6], # route includes depot (6) as final destination; proc_times only covers actual operations
        #                   [0.15,0.20,0.30])
        # else:
        #     return Job(self.job_counter, 3,
        #                   [2,5,1,4,3,6], # route includes depot (6) as final destination; proc_times only covers actual operations
        #                   [0.15,0.10,0.35,0.20,0.20])

        jobs = [
        (1, [10,20,30,40,50,60,70], [66, 68, 175, 85, 199, 129 ]),
        (2, [10,20,30,40,50,60,70], [66, 168, 239, 85, 199, 129 ]),
        (3, [10,20,30,40,50,60,70], [66, 193, 260, 85, 199, 129 ]),
        (4, [10,20,30,40,50,60,70], [66, 18, 209, 85, 100, 129 ]),
        (5, [10,20,30,40,50,60,70], [66, 168, 239, 85, 199, 129 ])
        ]

        probabilities = [0.35, 0.10, 0.10, 0.35, 0.10]

        job_type, route, proc_times = random.choices(
        jobs,
        weights=probabilities,
        k=1
        )[0]

        return Job(self.job_counter, job_type, route, proc_times)

    def travel_time(self, i, j):
        """Return the travel time (seconds)"""
        import numpy as np

        nodes = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

        # Create a mapping from node label to matrix index
        node_idx = {node: i for i, node in enumerate(nodes)}

        travel_matrix = np.array([
            [0, 28, 39, 35, 26, 35, 45, 62, -1, 31, 40],
            [28, 0, 12, 30, 31, 38, 56, 73, 65, 36, 35],
            [39, 12, 0, 19, 20, 27, 45, 62, 53, 25, 24],
            [35, 30, 19, 0, 7, 14, 33, 49, 40, 12, 5],
            [26, 31, 20, 7, 0, 15, 33, 50, -1, 5, 12],
            [35, 38, 27, 14, 15, 0, 19, 36, 27, 20, 19],
            [45, 56, 45, 33, 33, 19, 0, 17, -1, 38, 38],
            [62, 73, 62, 49, 50, 36, 17, 0, -1, 55, 54],
            [-1, 65, 53, 40, -1, 27, -1, -1, 0, 52, 45],
            [31, 36, 25, 12, 5, 20, 39, 55, 52, 0, 17],
            [40, 35, 24, 5, 12, 19, 38, 54, 45, 17, 0]
        ])

        return travel_matrix[node_idx[i], node_idx[j]]

    # ============================================================
    # SEQUENCING AND DISPATCHING RULES
    # ============================================================

    # def select_job(self, queue):
    #     """Selection rule for jobs at machines"""
    #     if self.machine_rule == "FIFO":
    #         return queue.pop(0)
    #     elif self.machine_rule == "LRO": 
    #         # least remaining operations; prioritises jobs close to completion
    #         job = min(queue, key=lambda j: j.remaining_ops())
    #     elif self.machine_rule == "SST":
    #         # smallest mean service time of the current operation
    #         job = min(queue, key=lambda j: j.proc_times[j.current_op])       

    #     queue.remove(job)
    #     return job

    def select_transport_job(self, available_agvs, transport_queue):
        """Select which AGV and which job to dispatch next"""
        # All SDF variants — primary criterion: distance; secondary: tie-breaker
        secondary = self.agv_rule[4:]   # for "FIFO", "LRO", "SST"

        def key(pair, sec=secondary):
            a, j = pair
            dist = self.travel_time(a.location, j.current_location)
            if sec == "LRO":
                tie = j.remaining_ops()
            elif sec == "SST":
                tie = j.proc_times[j.current_op] if j.current_op < len(j.proc_times) else 0
            elif sec == "FIFO":
                tie = 0    
            return (dist, tie)
        
        agv, job = min(((a, j) for a in available_agvs for j in transport_queue), key=key)
        available_agvs.remove(agv)
        transport_queue.remove(job)
        return agv, job


    def select_replenishment_job(self, available_amrs, replenishment_queue):
        """Select which AMR and which job to dispatch next"""
        if available_amrs and replenishment_queue:
            amr = available_amrs.pop(0)      # first available AMR
            job = replenishment_queue.pop(0) # first job

            return amr, job
    

    # ============================================================
    # CORE LOGIC
    # ============================================================

    # def request_workstations(self, ws):
    #     """Request workstations to process jobs in the waiting queue"""
    #     workstation = self.workstations[ws-1]
    #     # Continue as long as jobs are waiting and workstation is available
    #     while workstation.queue and workstation.is_available():
    #         # Get a job from the queue
    #         job = self.select_job(workstation.queue)
    #         # Record waiting time of job
    #         if job.ws_entry_time is not None:
    #             job.total_ws_wait += self.now - job.ws_entry_time
    #         job.ws_entry_time = None

    #         # Assign job to a machine in the workstation and seize the machine
    #         workstation.seize(job)
    #         job.start_service_time = self.now
    #         job.resource_id = ws
    #         pt = job.current_pt()

    #         if self.debug:
    #             print(f"Job {job.id} starts processing on workstation {ws} at time {self.now:.2f}")

    #          # Schedule job completion on workstation
    #         self.add_event(Event(Event.PROCESS_COMPLETE, 
    #                              self.now + pt, 
    #                              job, 
    #                              resource=workstation, 
    #                              location=ws))

    def request_agvs(self):
        """Request agvs to transport jobs in the transport queue"""
        # Select available agvs
        available_agvs = []
        for agv in self.agvs:
            if not agv.is_busy and agv.available_time <= self.now:
                available_agvs.append(agv)
        # Continue as long as transports are waiting and agvs are available
        while available_agvs and self.transport_queue:
            # Find the AGV-job pair
            agv, job = self.select_transport_job(available_agvs, self.transport_queue)
            # Set the chosen AGV busy
            agv.is_busy = True

            # Record wait for transport
            if job.transport_entry_time is not None:
                job.total_transport_wait += self.now - job.transport_entry_time
            job.transport_entry_time = None

            # Set next destinatin of job
            if job.current_op >= len(job.route):
                print("Error: job.current_op out of range")
                print("job id:", job.id)
                print("current_op:", job.current_op)
                print("route:", job.route)
            
            destination = job.route[job.current_op]
            # Unblock the machine unit of the workstation
            if job.current_location != 00:
                current_ws_location = job.current_location
                ws = next(ws for ws in self.workstations if ws.location == current_ws_location)
                if current_ws_location != job.route[-1]:
                    # Remove the job from the workstation and the blocking list
                    ws.release(job.id)
                    ws.blocked_entities = [e for e in ws.blocked_entities if e.id != job.id]
                    # When the blocked job is picked up, trigger the workstation to process the next waiting job --> not per se done!
                    #self.request_workstations(ws)

            if job.current_location == 10 and len(self.waiting_prep_station) > 0:
                job_to_transport = self.waiting_prep_station.pop(0)
                self.transport_queue.append(job_to_transport)
                job_to_transport.time_to_transport = self.now if self.collecting else None
            
            sequential_ws = [20,30,40,50,60]
            if job.current_location in sequential_ws:
                current_ws = next(ws for ws in self.workstations if ws.location == job.current_location)
                index_previous = self.workstations.index(current_ws) - 1 
                previous_location = self.workstations[index_previous]
                if len(previous_location.blocked_entities) > 0:
                    job_to_transport = previous_location.blocked_entities[0]
                    self.transport_queue.append(job_to_transport)
                    job_to_transport.time_to_transport = self.now


            
            
            # Collect statistics
            empty = self.travel_time(agv.location, job.current_location)
            loaded = self.travel_time(job.current_location, destination)

            if self.collecting:
                self.agv_empty_time += empty
                self.agv_loaded_time += loaded

            if self.debug:
                print(f"Job {job.id} starts being transported by AGV {agv.id} at time {self.now:.2f}")

            # Schedule transport completion on AGVs
            self.add_event(Event(Event.TRANSPORT_COMPLETE, 
                                 self.now + empty + loaded, 
                                 job, 
                                 resource=agv, 
                                 location=destination))

            # Set AGV location after the transport
            agv.location = destination


    def request_amrs(self):
            """Request agvs to transport jobs in the transport queue"""
            # Select available amrs
            available_amrs = []
            for amr in self.amrs:
                if not amr.is_busy and amr.available_time <= self.now:
                    available_amrs.append(amr)
            # Continue as long as replenishments are waiting and amrs are available
            while available_amrs and self.replenishment_queue:
                # Find the AMR-job pair
                amr, job = self.select_replenishment_job(available_amrs, self.replenishment_queue)
                # Set the chosen AMR busy
                amr.is_busy = True

                # Record wait for replenishment
                if job.replenishment_entry_time is not None:
                    job.total_replenishment_wait += self.now - job.replenishment_entry_time
                job.replenishment_entry_time = None

                # # Set next destinatin of job
                # destination = job.route[job.current_op]
                # # Unblock the machine unit of the workstation
                # current_ws_location = job.current_location
                # ws = next(ws for ws in self.workstations if ws.location == current_ws_location)
                # if current_ws_location != job.route[-1]:
                #     # Remove the job from the workstation and the blocking list
                #     ws.release(job.id)
                #     ws.blocked_entities = [e for e in ws.blocked_entities if e.id != job.id]
                #     # When the blocked job is picked up, trigger the workstation to process the next waiting job --> not per se done!
                #     #self.request_workstations(ws)
                destination = job.route[0]
                time_to_depot = self.travel_time(amr.location, 80)
                loading_time_full_trolley = 3
                time_to_travel = self.travel_time(80, destination)
                unloading_time_full_trolley = 3
                loading_time_empty_trolley = 3
                time_to_travel_back = self.travel_time(destination, 80)
                unloading_time_empty_trolley = 3
                

                empty = time_to_depot 
                loaded = time_to_travel + loading_time_full_trolley + loading_time_empty_trolley + time_to_travel_back + unloading_time_full_trolley + unloading_time_empty_trolley
                
                total_time_needed = empty + loaded
                time_to_supply = time_to_depot + loading_time_full_trolley + time_to_travel + unloading_time_full_trolley
                time_to_return = loading_time_empty_trolley + time_to_travel_back + unloading_time_empty_trolley
                # Collect statistics


                if self.collecting:
                    self.amr_empty_time += empty
                    self.amr_loaded_time += loaded

                if self.debug:
                    print(f"Job {job.id} starts being transported by AMR {amr.id} at time {self.now:.2f}")

                # Schedule transport completion on AGVs
                self.add_event(Event(Event.REPLENISHMENT_COMPLETE, 
                                    self.now + time_to_supply, 
                                    job, 
                                    resource=amr, 
                                    location=destination))

                # Set AGV location after the transport
                amr.location = 80
    # ============================================================
    # EVENTS
    # ============================================================

    def process_job_arrival_event(self, event):
        """Process arrival events"""
        assert event.event_type == Event.JOB_ARRIVAL

        job = self.generate_job()
        job.arrival_time = self.now

        if self.debug:
            print(f"Job {job.id} type {job.type} arrives at the input/output station at time {self.now:.2f}")

        self.job_counter += 1

        #check whether next workstation (current operation) is idle and resourced
        first_ws = self.workstations[job.current_op]
        if not first_ws.is_busy and len(first_ws.blocked_entities) == 0 and first_ws.resources > 0:
            self.transport_queue.append(job)
            job.transport_entry_time = self.now if self.collecting else None
        else:
            self.waiting_prep_station.append(job)


        # Schedule the next arrival 
        self.add_event(Event(Event.JOB_ARRIVAL, 
                             self.now + self.get_inter_arrival_time(),
                             None))

        # Check if agvs are available to transport this job
        self.request_agvs()

    def process_transport_completion_event(self, event):
        """Process transport events"""
        assert event.event_type == Event.TRANSPORT_COMPLETE

        job = event.job
        ws_location = event.location
        ws = next(ws for ws in self.workstations if ws.location == ws_location)
        agv = event.resource

        # Set job current location
        job.current_location = ws_location

        
        # Check if job arrived at depot after all operations
        if ws_location == job.route[-1]:
            # Collect statistics
            job.departure_time = self.now
            self.completed_jobs.append(job)

            agv.is_busy = False

            # Check if agvs can transport more jobs
            self.request_agvs()

        else:
            # # Add job to the queue of destination workstation
            # job.ws_entry_time = self.now if self.collecting else None
            # self.workstations[ws-1].queue.append(job)

            agv.is_busy = False

            # # Check if workstation is available to process this job

            # self.request_workstations(ws)

            ws.seize(job)
            job.start_service_time = self.now
            job.resource_id = ws.id
            


            index = self.workstations.index(ws)
            processing_time = job.proc_times[index]

            if self.debug:
                print(f"Job {job.id} starts processing on workstation {ws} at time {self.now:.2f}")

             # Schedule job completion on workstation
            self.add_event(Event(Event.ASSEMBLY_COMPLETE, 
                                 self.now + processing_time, 
                                 job, 
                                 resource=ws, 
                                 location=ws_location))

            # Check if agvs can transport more jobs
            self.request_agvs()

    def process_job_completion_event(self, event):
        """Process job completion events"""
        assert event.event_type == Event.ASSEMBLY_COMPLETE

        job = event.job
        ws_location = event.location
        ws = next(ws for ws in self.workstations if ws.location == ws_location)

        # When processing finishes, the job stays in current_entities (blocking the machine unit) and now in blocked_entities
        ws.blocked_entities.append(job)
        ws.release(job)
        if ws.resources != None:
            ws.resources = ws.resources - 1

        # advance operation
        if ws.location != 70:
            job.current_op += 1

        #check whether next workstation (current operation) is idle and resourced
        if ws.location != 70:
            next_ws = self.workstations[job.current_op]
            if next_ws.replenishment_level == None:
                if not next_ws.is_busy and len(next_ws.blocked_entities) == 0:
                    self.transport_queue.append(job)
                    job.transport_entry_time = self.now if self.collecting else None

            else:
                if not next_ws.is_busy and len(next_ws.blocked_entities) == 0 and next_ws.resources > 0:
                    self.transport_queue.append(job)
                    job.transport_entry_time = self.now if self.collecting else None
                
        # if ws_location != 10:
        #     previous_ws = self.workstations[job.current_op - 2]
            
            #check whether there is job blocked in upstream workstation and generate transport task for this one
            # if ws_location == 10 and len(self.waiting_prep_station) > 0:
            #     job_to_transport = self.waiting_prep_station[0]
            #     self.transport_queue.append(job_to_transport)
            #     job_to_transport.transport_entry_time = self.now if self.collecting else None
            # elif len(previous_ws.blocked_entities) > 0:
            #     job_to_transport = previous_ws.blocked_entities[0]
            #     self.transport_queue.append(job_to_transport)
            #     job_to_transport.transport_entry_time = self.now if self.collecting else None
        

        # Check if agvs are available to transport these jobs
        self.request_agvs()

        # Check if workstation needs replenishment
        if ws.replenishment_level != None:
            if ws.resources == ws.replenishment_level:
                amount_of_tasks_needed = ws.trolley_spots - ws.replenishment_level
                while amount_of_tasks_needed > 0:
                    self.replenishment_counter += 1
                    replenishment_task = Job(self.replenishment_counter, "Replenishment", [ws_location], None)
                    self.replenishment_queue.append(replenishment_task)
                    replenishment_task.replenishment_entry_time = self.now if self.collecting else None 
                    amount_of_tasks_needed = amount_of_tasks_needed - 1

        
        self.request_amrs()



        # self.request_workstations(ws)
    def process_replenishment_completion_event(self, event):
        """Process transport events"""
        assert event.event_type == Event.REPLENISHMENT_COMPLETE

        job = event.job
        ws_location = event.location
        ws = next(ws for ws in self.workstations if ws.location == ws_location)
        amr = event.resource

        ws.resources = ws.resources + 1

            # Set job current location
        job.current_location = ws_location

        destination = job.route[0]
        time_to_depot = self.travel_time(amr.location, 80)
        loading_time_full_trolley = 3
        time_to_travel = self.travel_time(80, destination)
        unloading_time_full_trolley = 3
        loading_time_empty_trolley = 3
        time_to_travel_back = self.travel_time(destination, 80)
        unloading_time_empty_trolley = 3
        time_to_return = loading_time_empty_trolley + time_to_travel_back + unloading_time_empty_trolley

        amr.is_busy = False
        amr.available_time = self.now + time_to_return
            
            
        self.request_amrs()

    # ============================================================
    # ENGINE
    # ============================================================

    def add_event(self, event):
        """Add event to future events"""
        assert event.time >= self.now

        if self.debug:
            print(f">> Schedule {event}")
        heapq.heappush(self.events, event)

    def get_next_event(self) -> Event:
        """Get next event and remove it from the heapq.
            Return None if there are no future events"""
        return heapq.heappop(self.events) if self.events else None

    def run(self, debug_flag, warmup, length):
        """Run simulation"""
        # Initialize parameters and events
        self.debug = debug_flag
        self.add_event(Event(Event.JOB_ARRIVAL, 0, None))

        while self.events:
            # Get the next event in the queue
            event = self.get_next_event()
            self.now = event.time
            self.update_time_stats()

            if self.now > warmup:
                self.collecting = True

            if self.now > length:
                break

            if event.event_type == Event.JOB_ARRIVAL:
                self.process_job_arrival_event(event)

            elif event.event_type == Event.TRANSPORT_COMPLETE:
                self.process_transport_completion_event(event)

            elif event.event_type == Event.ASSEMBLY_COMPLETE:
                self.process_job_completion_event(event)

            elif event.event_type == Event.REPLENISHMENT_COMPLETE:
                self.process_replenishment_completion_event(event)

            # Process events
            if self.debug:
                print(f"Execute {event}")

        return self.get_stats(warmup)

    # ============================================================
    # KPIs
    # ============================================================

    def update_time_stats(self):
        """Update statistics after each event"""
        dt = self.now - self.last_event_time

        if self.collecting:

            for i in range(len(self.workstations)):
                q_len = len(self.workstations[i].queue)
                blocked = len(self.workstations[i].blocked_entities)
                busy = len(self.workstations[i].current_entities) - blocked  # actively processing only

                self.area_queue[i]   += q_len   * dt
                self.area_busy[i]    += busy    * dt
                self.area_blocked[i] += blocked * dt

                if q_len > self.max_queue[i]:
                    self.max_queue[i] = q_len

            tq_len = len(self.transport_queue)
            self.area_transport_queue += tq_len * dt
            if tq_len > self.max_transport_queue:
                self.max_transport_queue = tq_len

            total = sum(len(ws.queue) + len(ws.current_entities)
                        for ws in self.workstations) + tq_len
            self.area_system += total * dt

        self.last_event_time = self.now


    def get_stats(self, warmup):
        """Collect statistics"""
        T = self.now - warmup

        completed = [j for j in self.completed_jobs if j.departure_time > warmup]
        print("Total completed jobs:", len(self.completed_jobs))
        if len(self.completed_jobs) > 0:
            print( "Last completion time:", max(j.departure_time for j in self.completed_jobs))
        

        if len(completed) == 0:
            print("WARNING: No completed jobs after warmup!")
            return None

        flow_time = [j.departure_time - j.arrival_time for j in completed]

        throughput = len(completed) / T * 8



        return {
            "throughput": throughput,
            "flow_time": np.mean(flow_time),
            "avg_queue": [self.area_queue[i] / T for i in range(len(self.workstations))],
            "max_queue": self.max_queue,
            "busy": [
                self.area_busy[i] / (T*self.workstations[i].capacity)
                for i in range(len(self.workstations))
            ],
            "blocked": [
                self.area_blocked[i] / (T * self.workstations[i].capacity)
                for i in range(len(self.workstations))
            ],
            "agv_loaded": self.agv_loaded_time / (T * len(self.agvs)),
            "agv_empty": self.agv_empty_time / (T * len(self.agvs)),
            "avg_transport_queue": self.area_transport_queue / T,
            "max_transport_queue": self.max_transport_queue,
            "avg_system": self.area_system / T,
            #"avg_ws_wait": np.mean([j.total_ws_wait for j in completed]),
            "avg_transport_wait": np.mean([j.total_transport_wait for j in completed]),
        }


# ============================================================
# EXPERIMENT
# ============================================================
def _run_single(args):
    """Top-level worker — must be at module level so multiprocessing can pickle it.
    Each spawned process seeds its own independent RNG."""
    r, machines_config, n_agvs, n_amrs, agv_rule, amr_rule, debug_on, warmup, length = args
    random.seed(r)
    np.random.seed(r)
    sim = Simulation(machines_config, n_agvs, n_amrs, agv_rule, amr_rule)
    return sim.run(debug_on, warmup, length)

def run_experiment():
    # Model parameters
    #machine configuration: for each machine a tuple with (location, reorder level for replenishment, max trolly spots)
    machines_config = {10: (10, 1, 3), 20: (20 , 1, 3), 30: (30, 1, 3), 40: (40, None, None), 50: (50, 1, 4), 60: (60, None, None), 70: (70,None, None)}# Number of individual machines in 5 wS
    n_agvs = 2 
    n_amrs = 2                             # Number of AGVs
    agv_rule = "SDF-FIFO"
    amr_rule = "FIFO"

    # Debug enabled
    debug_on = False
    max_n_sim = 5 # 50
    warmup = 50000 # 200
    length = 300000 # 1000
    n_workers = 10 # set to your number of logical CPU cores

    # One tuple per replication
    args = [
        (r, machines_config, n_agvs, n_amrs, agv_rule, amr_rule, debug_on, warmup, length)
        for r in range(max_n_sim)
        ]

    results = [None] * max_n_sim

    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        # Submit all replications; record which future maps to which index
        futures = {executor.submit(_run_single, a): i for i, a in enumerate(args)}

        # Collect as they finish — completion order is non-deterministic
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            print(f"Replication {i + 1:>3} / {max_n_sim} done")

    print_results(results)

def print_results(results):
    results = [r for r in results if r is not None]
    if len(results) ==0:
        print("No valid replications ciompleted")
        return

    
    """Print statistics"""
    avg_queue   = np.mean([r["avg_queue"]            for r in results], axis=0)
    max_queue   = np.mean([r["max_queue"]            for r in results], axis=0)
    busy        = np.mean([r["busy"]                 for r in results], axis=0)
    blocked     = np.mean([r["blocked"]              for r in results], axis=0)
    throughput  = np.mean([r["throughput"]           for r in results])
    flow_time   = np.mean([r["flow_time"]            for r in results])
    agv_loaded  = np.mean([r["agv_loaded"]           for r in results])
    agv_empty   = np.mean([r["agv_empty"]            for r in results])
    avg_tq      = np.mean([r["avg_transport_queue"]  for r in results])
    max_tq      = np.mean([r["max_transport_queue"]  for r in results])
    avg_system  = np.mean([r["avg_system"]           for r in results])
    
    avg_tp_wait = np.mean([r["avg_transport_wait"]   for r in results])

    LW = 35   # label width
    SW = 9    # station/value column width
    CW = 8    # per-station column width
    sep = "\u2500" * (LW + SW + CW * 6)

    # --- header ---
    print(f"{'Performance measure':<{LW}}{'Station':>{SW}}", end="")
    for i in range(1, 7):
        print(f"{i:>{CW}}", end="")
    print()
    print(sep)

    # --- per-station rows ---
    def station_row(label, ws_vals, last):
        line = f"{label:<{LW}}{'':{SW}}"
        for v in ws_vals:
            line += f"{v:>{CW}.2f}"
        line += f"{last:>{CW}}" if isinstance(last, str) else f"{last:>{CW}.2f}"
        print(line)

    station_row("Proportion machines busy",    busy,        "-")
    station_row("Proportion machines blocked", blocked,     "-")
    station_row("Average number in queue",     avg_queue,   round(avg_tq, 2))

    # maximum: integer formatting
    line = f"{'Maximum number in queue':<{LW}}{'':{SW}}"
    for v in max_queue:
        line += f"{int(round(v)):>{CW}}"
    line += f"{int(round(max_tq)):>{CW}}"
    print(line)

    print(sep)

    # --- overall stats ---
    print(f"{'Average daily throughput'     :<{LW}}{throughput:>{SW}.2f}")
    print(f"{'Average number in queue'      :<{LW}}{avg_system:>{SW}.2f}")
    print(f"{'Average time in system'       :<{LW}}{flow_time:>{SW}.2f}")
    
    print(f"{'Average total wait for transport':<{LW}}{avg_tp_wait:>{SW}.2f}")  
    print(f"{'Proportion agvs moving loaded':<{LW}}{agv_loaded:>{SW}.2f}")
    print(f"{'Proportion atvs moving empty' :<{LW}}{agv_empty:>{SW}.2f}")

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    run_experiment()