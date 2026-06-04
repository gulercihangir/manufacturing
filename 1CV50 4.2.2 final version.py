import heapq
import random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as st

# TRAVEL TIME are obtained from case descriptionn
TRAVEL_TIMES = {
    (0,   0):  0,  (0,  10): 28, (0,  20): 39, (0,  30): 35,
    (0,  40): 26,  (0,  50): 35, (0,  60): 45, (0,  70): 62,
    (0,  90): 31,  (0, 100): 40,

    (10,  0): 28,  (10, 10):  0, (10, 20): 12, (10, 30): 30,
    (10, 40): 31,  (10, 50): 38, (10, 60): 56, (10, 70): 73,
    (10, 90): 36,  (10,100): 35,

    (20,  0): 39,  (20, 10): 12, (20, 20):  0, (20, 30): 19,
    (20, 40): 20,  (20, 50): 27, (20, 60): 45, (20, 70): 62,
    (20, 90): 25,  (20,100): 24,

    (30,  0): 35,  (30, 10): 30, (30, 20): 19, (30, 30):  0,
    (30, 40):  7,  (30, 50): 14, (30, 60): 33, (30, 70): 49,
    (30, 90): 12,  (30,100):  5,

    (40,  0): 26,  (40, 10): 31, (40, 20): 20, (40, 30):  7,
    (40, 40):  0,  (40, 50): 15, (40, 60): 33, (40, 70): 50,
    (40, 90):  5,  (40,100): 12,

    (50,  0): 35,  (50, 10): 38, (50, 20): 27, (50, 30): 14,
    (50, 40): 15,  (50, 50):  0, (50, 60): 19, (50, 70): 36,
    (50, 80): 27,  (50, 90): 20, (50,100): 19,

    (60,  0): 45,  (60, 10): 56, (60, 20): 45, (60, 30): 33,
    (60, 40): 33,  (60, 50): 19, (60, 60):  0, (60, 70): 17,
    (60, 90): 38,  (60,100): 38,

    (70,  0): 62,  (70, 10): 73, (70, 20): 62, (70, 30): 49,
    (70, 40): 50,  (70, 50): 36, (70, 60): 17, (70, 70):  0,
    (70, 90): 55,  (70,100): 54,

    (90,  0): 31,  (90, 10): 36, (90, 20): 25, (90, 30): 12,
    (90, 40):  5,  (90, 50): 20, (90, 60): 39, (90, 70): 55,
    (90, 90):  0,  (90,100): 17,

    (100, 0): 40,  (100,10): 35, (100,20): 24, (100,30):  5,
    (100,40): 12,  (100,50): 19, (100,60): 38, (100,70): 54,
    (100,90): 17,  (100,100): 0,
}

L_TIME = 3   # loading time (s)
U_TIME = 3   # unloading time (s)
PARKING_NODE = 90

# FIXED TRANSPORT REQUESTS (Table 4 from case description)
# Each number represents: (request_id, release_time, source_node, dest_node)
REQUESTS = [
    (1,   0,  0,  10),
    (2,  66, 10,  20),
    (3,  68, 20,  30),
    (4,  85, 30,  40),
    (5, 129, 40,  50),
    (6, 175, 50,  60),
    (7, 199, 60,  70),
]

class Event(object):
    ENTITY_ARRIVAL   = 0   # a transport request becomes available
    ENTITY_COMPLETE  = 1   # an AGV finishes a transport task
    RETURN_COMPLETE  = 2   # an AGV finishes returning to the parking node
 
    EVENT_TO_STR = {
        0: "ENTITY_ARRIVAL",
        1: "ENTITY_COMPLETE",
        2: "RETURN_COMPLETE",
    }
 
    def __init__(self, event_type, time, entity, resource_id=None):
        self.event_type  = event_type
        self.time        = time
        self.entity      = entity        # transport request (None for RETURN_COMPLETE)
        self.resource_id = resource_id   # which AGV
 
    def __lt__(self, other):
        # FCFS tie-breaking: earlier event time first, then by request id
        if self.time == other.time:
            if self.entity is not None and other.entity is not None:
                return self.entity.id < other.entity.id
            return self.time < other.time
        return self.time < other.time
 
    def __str__(self):
        resource_info = f" on AGV {self.resource_id}" if self.resource_id is not None else ""
        entity_info   = f" for Request {self.entity.id}" if self.entity is not None else ""
        return (f"Event {self.EVENT_TO_STR[self.event_type]}"
                f"{entity_info}{resource_info} at time {self.time:.2f}")

class Resource(object):
    #Represents a single AGV with a physical position and availability tracking.
 
    def __init__(self, resource_id, capacity):
        self.id               = resource_id
        self.capacity         = capacity        # always 1 for an AGV
        self.current_entities = []              # request currently being served
        self.current_position = PARKING_NODE    # both AGVs start at node 90
        self.available_at     = 0               # time this AGV becomes free
 
    def seize(self, entity):
        """Mark this AGV as busy serving the given request."""
        self.current_entities.append(entity)
        return self.id
 
    def release(self, entity_id):
        """Free this AGV after completing a task."""
        self.current_entities = [e for e in self.current_entities if e.id != entity_id]
 
    def is_available(self):
        """True only if the AGV is not currently serving AND not returning to parking."""
        return len(self.current_entities) < self.capacity
 

class Entity(object):
    # this represents a single request

    def __init__(self, entity_id, release_time, source, dest):
        self.id           = entity_id    # request id
        self.release_time = release_time # when the request becomes available
        self.source       = source       # pickup node
        self.dest         = dest         # dropo node
        self.arrival_time = None         # time request entered the queue
        self.start_times  = {}           # when AGV started serving 
        self.end_times    = {}           # when AGV finished serving 
        self.departure_time = None       # time request was fully completed
        self.current_machine = None      # which AGV served this request



class Simulation(object):
    #DES for Exercise 4.2.2:
    #2 AGVs serve 7 fixed requests using real travel times and AGVs start at parking node 90.
    #Dispatching: FCFS by release time, assigned to earliest available AGV 
    #Service = empty travel (current pos → source) + load + loaded travel (source → dest) + unload.
    

    def __init__(self, num_agvs, agv_capacities):
        self.now            = 0      # simulation clock
        self.events         = []     # future event list (min-heap)
        # Creating one Resource per AGV, each starting at node 90
        self.machines       = [Resource(i, capacity=agv_capacities[i]) for i in range(num_agvs)]
        self.queue          = []     # shared waiting queue of released requests (FCFS)
        self.debug          = False
        self.completed_jobs = []     # all requests that finished service

        # Define process flow — requests go through one AGV step then exit
        # (keeping template 2 structure for consistency)
        self.machine_sequence = {
            0: None,   # AGV 1: after serving, request exits
            1: None    # AGV 2: after serving, request exits
        }


    def add_event(self, event):
        assert event.time >= self.now
        if self.debug:
            print(f">> Schedule {event}")
        heapq.heappush(self.events, event)

    def get_next_event(self):
        # for returning the earliest event
        return heapq.heappop(self.events) if self.events else None

    def get_earliest_available_agv(self):
        #this function returns the AGV that will become free the soonest.
        #Among free AGVs, pick by lowest index.
        #Among busy AGVs, pick by smallest available_at time
       
        free_agvs = [agv for agv in self.machines if agv.is_available()]
        if free_agvs:
            # Among currently free AGVs, pick lowest index
            return min(free_agvs, key=lambda a: a.id)
        return None


    def get_service_time(self, agv, request):
    
        # travel + loading time (3s)+ loaded travel + unloading time (3s)
        #AGV may need to waitat the source if it arrives before the request release time).
        
        empty_travel  = TRAVEL_TIMES[(agv.current_position, request.source)]
        loaded_travel = TRAVEL_TIMES[(request.source, request.dest)]

        # AGV arrives at source at: now + empty_travel
        # But it can only load after the request is released
        arrive_at_source = self.now + empty_travel
        start_loading    = max(arrive_at_source, request.release_time)  # wait if early

        # Total completion time from now
        completion_time = start_loading + L_TIME + loaded_travel + U_TIME
        service_time    = completion_time - self.now  # duration from now to done

        return service_time, completion_time

    def schedule_return_to_parking(self, agv):
        
        #After completing a task with no pending work, send the AGV back to node 90.
        #The AGV is marked busy (capacity seized with a dummy sentinel so is_available returns False) until it reaches the parking node.
    
        if agv.current_position == PARKING_NODE:
            # Already at parking, thus nothing to do, stays available 
            if self.debug:
                print(f"AGV {agv.id} already at parking node, stays idle.")
            return
 
        travel_time    = TRAVEL_TIMES[(agv.current_position, PARKING_NODE)]
        arrive_parking = self.now + travel_time
 
        if self.debug:
            print(f"AGV {agv.id} returning to parking: "
                  f"node {agv.current_position} -> 90, "
                  f"travel={travel_time}s, arrives at t={arrive_parking:.1f}")
 
        # Use a sentinel entity (id=-agv.id-1) to mark the AGV as in-transit
        sentinel = Entity(-agv.id - 1, self.now, agv.current_position, PARKING_NODE)
        agv.seize(sentinel)
        agv.available_at = arrive_parking
 
        self.add_event(Event(Event.RETURN_COMPLETE, arrive_parking,
                             entity=sentinel, resource_id=agv.id))

    def setup(self):
        #Schedules all 7 fixed transport requests as arrival events at their release times
        for req_id, release_time, source, dest in REQUESTS:
            entity = Entity(req_id, release_time, source, dest)
            # Request becomes available at its release time
            self.add_event(Event(Event.ENTITY_ARRIVAL, release_time, entity))

        if self.debug:
            print(f"Scheduled {len(REQUESTS)} transport requests")
            

    def process_arrival_event(self, event):
        #this function handles a request
        assert event.event_type == Event.ENTITY_ARRIVAL

        request              = event.entity
        request.arrival_time = self.now   # time it entered the queue

        # Request to the queue
        self.queue.append(request)

        if self.debug:
            print(f"Request {request.id} (src={request.source}→dst={request.dest}) "
                  f"released at t={self.now:.2f}")

        # Try to dispatch a free AGV immediately
        self.request_machines()



    def process_departure_event(self, event):
        """Handle an AGV finishing a transport task"""
        assert event.event_type == Event.ENTITY_COMPLETE

        request              = event.entity
        agv_id               = event.resource_id
        request.departure_time = self.now
        request.end_times[agv_id] = self.now

        if self.debug:
            print(f"Request {request.id} completed by AGV {agv_id} at t={self.now:.2f}")

        # Update AGV position to the destination of the completed request
        self.machines[agv_id].current_position = request.dest
        self.machines[agv_id].available_at     = self.now

        # Release the AGV
        self.machines[agv_id].release(request.id)

        # Record as completed
        self.completed_jobs.append(request)

        # Try to dispatch this AGV to the next queued request
        dispatched = self.request_machines() # Try to immediately dispatch a queued request to this now-free AGV
        if not dispatched: # If nothing was dispatched, send this AGV back to parking
                self.schedule_return_to_parking(self.machines[agv_id])

    def process_return_complete_event(self, event):
        #An AGV has finished returning to the parking node
        
        assert event.event_type == Event.RETURN_COMPLETE
 
        agv_id  = event.resource_id
        agv     = self.machines[agv_id]
        sentinel = event.entity
 
        # Release the sentinel so the AGV is truly available again
        agv.release(sentinel.id)
        agv.current_position = PARKING_NODE
        agv.available_at     = self.now
 
        if self.debug:
            print(f"AGV {agv_id} arrived at parking node 90 at t={self.now:.2f}, now idle.")
 
        # Check if any request queued up while the AGV was returning
        self.request_machines()

    def request_machines(self):
        #FCFS Each request goes to the first free AGV .
        while self.queue and (agv := self.get_earliest_available_agv()) is not None:
            # Take the next request from the queue (FCFS by release time)
            request = self.queue.pop(0)

            # Seize the AGV
            agv_id  = agv.seize(request)
            request.start_times[agv_id] = self.now
            request.current_machine     = agv_id

            if self.debug:
                print(f"Request {request.id} assigned to AGV {agv_id} at t={self.now:.2f} "
                      f"(AGV at node {agv.current_position})")

            # cmputing service times considering real travel times and release time
            service_time, completion_time = self.get_service_time(agv, request)
            agv.available_at = completion_time

            # schedule the completion event
            self.add_event(Event(Event.ENTITY_COMPLETE,completion_time,request,resource_id=agv_id))

    def run(self, debug_flag, num_jobs):
        #running the simulation until all requests are conpleted
        self.debug = debug_flag
        self.setup()

        event_handlers = {
            Event.ENTITY_ARRIVAL:  self.process_arrival_event,
            Event.ENTITY_COMPLETE: self.process_departure_event,
            Event.RETURN_COMPLETE: self.process_return_complete_event,
        }

        # Run until all requests are done
        while self.events and len(self.completed_jobs) < num_jobs:
            event = self.get_next_event()
            if not event:
                break

            self.now = event.time

            if self.debug:
                print(f"\nExecute {event}")

            event_handlers[event.event_type](event)

        
        print("\n" + "=" * 60)
        print("  results for 4.2.2")
        print("=" * 60)
        print(f"  {'Req':>4} {'AGV':>4} {'Source':>7} {'Dest':>6} "
              f"{'Release':>8} {'Start':>7} {'Done':>7} {'Flow':>7}")
        print("  " + "-" * 58)

        for req in sorted(self.completed_jobs, key=lambda r: r.id):
            agv_id    = req.current_machine
            start     = req.start_times[agv_id]
            end       = req.end_times[agv_id]
            flow_time = end - req.arrival_time
            print(f"  {req.id:>4} {agv_id:>4} {req.source:>7} {req.dest:>6} "
                  f"{req.release_time:>8.1f} {start:>7.1f} {end:>7.1f} {flow_time:>7.1f}")

        makespan = max(req.departure_time for req in self.completed_jobs)
        print("  " + "-" * 58)
        print(f"  Makespan (completion of last request): {makespan:.1f} s")
        print("=" * 60)

        return makespan

if __name__ == "__main__":
    num_agvs       = 2        # two AGVs
    agv_capacities = [1, 1]   # each AGV serves one request at a time
    num_jobs       = len(REQUESTS)   # 7 fixed requests

    debug_on = True   # set True to trace every event step by step

    print("=" * 60)
    print("  Exercise 4.2.2 — AGV Transport between Stations")
    print("=" * 60)
    print(f"  AGVs: {num_agvs} | Requests: {num_jobs} | "
          f"Start position: node 90 (parking)")
    print(f"  Load time: {L_TIME}s | Unload time: {U_TIME}s")
    print("=" * 60)

    sim      = Simulation(num_agvs, agv_capacities)
    makespan = sim.run(debug_on, num_jobs)

    print("\n  VERIFICATION against hand-calculated lot-time diagram:")
    print(f"  Expected makespan : 261.0 s")
    print(f"  Simulated makespan: {makespan:.1f} s")
    if abs(makespan - 261.0) < 0.001:
        print(" Simulation matches the lot-time diagram")
    else:
        print(" Mismatch — check travel times or dispatch logic.")
