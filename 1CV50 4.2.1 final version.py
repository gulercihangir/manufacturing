import heapq
import random
import numpy as np

# our parameters for 4.2.1
ARRIVAL_RATE     = 1 / 120  # inter arrival time is 120 s
V_MIN            = 5        # minimum travel time s
V_MAX            = 73       # max travel time s
L_TIME           = 3        # loading s
U_TIME           = 3        # unloading s  ← was 2, must be 3
NUM_AGVS         = 2        # num of parallel AGV servers
HORIZON          = 300000   # simulation length s
WARMUP           = 50000    # we won't include information from warm-up period
NUM_RUNS         = 10       


class Event(object):
    """Represents one event in the DES"""
    ENTITY_ARRIVAL  = 0  # a request arrives
    ENTITY_COMPLETE = 1  # an AGV finishes serving

    EVENT_TO_STR = {
        0: "ENTITY_ARRIVAL",
        1: "ENTITY_COMPLETE"
    }

    def __init__(self, event_type, time, entity, resource_id=None):
        self.event_type  = event_type   # which type of event?
        self.time        = time         # scheduled time of this event
        self.entity      = entity       # the transport request involved
        self.resource_id = resource_id  # which AGV will handle the request?

    def __lt__(self, other):
        if self.time == other.time:
            return self.entity.id < other.entity.id  #according to the model shared in all models in collab, if events have the same time, ensure FCFS by comparing entity IDs
        return self.time < other.time

    def __str__(self):
        resource_info = f"on AGV {self.resource_id}" if self.resource_id is not None else ""
        return (f"Event {self.EVENT_TO_STR[self.event_type]} "
                f"for Request {self.entity.id} {resource_info} at time {self.time:.2f}")


class Resource(object):
    def __init__(self, resource_id, capacity):
        self.id               = resource_id   # aagv identifier
        self.capacity         = capacity      # max request is 1 per agv, num of entities that can be processed simultaneously 
        self.current_entities = []            # list of requests currently being served

    def seize(self, entity):
        #assigning request to this specific AGV
        self.current_entities.append(entity)
        return self.id

    def release(self, entity_id):
        #let this AGV available when it has finished
        self.current_entities = [e for e in self.current_entities if e.id != entity_id]

    def is_available(self):
        #Return True if it has capacity/available, if resource is available to process an entity 
        return len(self.current_entities) < self.capacity


class Entity(object):
    #a request moving in the system
    def __init__(self, entity_id):
        self.id                 = entity_id  # unique request identifier
        self.arrival_time       = None       # time this request entered the system
        self.start_service_time = None       # time an AGV started serving it
        self.departure_time     = None       # time service was completed
        self.resource_id        = None       # which AGV handled this request


class Simulation(object):
    #Arrivals : Poisson process, mean inter-arrival time = 120 s
    #Service  : loading (3s) + travel Uniform[5,73] + unloading (3s)
    def __init__(self, num_agvs, agv_capacities):
        self.now            = 0      # simulation clock
        self.events         = []     # future events list
        self.machines       = [Resource(i, capacity=agv_capacities[i]) for i in range(num_agvs)]
        self.queue          = []     # waiting queue bc of FCFS
        self.debug          = False  # True to print every event for record
        self.completed_jobs = []     # all requests that have finished service
        self.job_counters   = 0      # counter used to assign unique IDs to requests
        self.flow_times     = []     # flow time = waiting + service (after warmup)
        self.warmup_done    = False  # True once we pass the warmup

    def add_event(self, event):
        #Adding an event to the future event list
        assert event.time >= self.now
        if self.debug:
            print(f">> Schedule {event}")
        heapq.heappush(self.events, event)

    def get_next_event(self):
        #the earliest event"""
        return heapq.heappop(self.events) if self.events else None

    def get_available_machine(self):
        #Return the first available AGV or None
        for agv in self.machines:
            if agv.is_available():
                return agv
        return None

    def get_inter_arrival_time(self):
        #Mean inter-arrival = 1/lambda = 120 seconds
        return random.expovariate(ARRIVAL_RATE)

    def get_service_time(self):
        #Service time: load + uniform travel time + unload
        travel_time  = random.uniform(V_MIN, V_MAX)
        service_time = L_TIME + travel_time + U_TIME
        return service_time

    def setup(self):
        #Arranging the first arrival request to start the simulation"""
        first_arrival_time = self.get_inter_arrival_time()  
        first_entity       = Entity(self.job_counters)
        self.add_event(Event(Event.ENTITY_ARRIVAL, first_arrival_time, first_entity))

    def process_arrival_event(self, event):
        #Processing a request arrived
        assert event.event_type == Event.ENTITY_ARRIVAL

        request              = event.entity
        request.arrival_time = self.now  # record when it entered the system
        self.queue.append(request)

        if self.debug:
            print(f"Request {request.id} arrives and joins queue at t={self.now:.2f}")  

        # scheduling the next arrival — exponential is memoryless so,
        self.job_counters  += 1
        next_arrival_time   = self.now + self.get_inter_arrival_time()  # ← was next.arrival_time
        self.add_event(Event(Event.ENTITY_ARRIVAL, next_arrival_time, Entity(self.job_counters)))

        # try to start an AGV if one is free
        self.request_machines()

    def process_departure_event(self, event):
        #Handling an AGV finishing processing a request
        assert event.event_type == Event.ENTITY_COMPLETE

        request                = event.entity
        agv_id                 = event.resource_id
        request.departure_time = self.now

        if self.debug:
            print(f"Request {request.id} completed by AGV {agv_id} at t={self.now:.2f}")

        if self.warmup_done:
            flow_time = request.departure_time - request.arrival_time
            self.flow_times.append(flow_time)

        self.completed_jobs.append(request)
        self.machines[agv_id].release(request.id)
        self.request_machines()

    def request_machines(self):
        #Keep assigning as long as there are requests waiting and AGVs free
        while self.queue and (agv := self.get_available_machine()) is not None:
            request                    = self.queue.pop(0)
            agv_id                     = agv.seize(request)
            request.start_service_time = self.now
            request.resource_id        = agv_id

            if self.debug:
                print(f"Request {request.id} assigned to AGV {agv_id} at t={self.now:.2f}")

            service_time    = self.get_service_time()
            completion_time = self.now + service_time
            self.add_event(Event(Event.ENTITY_COMPLETE, completion_time, request, resource_id=agv_id))

    def run(self, debug_flag):
       #Run the sim until clock reaches HORIZON and only record after the warmup.
        self.debug = debug_flag
        self.setup()

        event_handlers = {Event.ENTITY_ARRIVAL:  self.process_arrival_event, Event.ENTITY_COMPLETE: self.process_departure_event,}

        while self.events:
            event = self.get_next_event()
            if not event:
                break
            if event.time > HORIZON:
                break
            self.now = event.time

            if not self.warmup_done and self.now >= WARMUP:
                self.warmup_done = True  #start record

            if self.debug:
                print(f"Execute {event}")

            event_handlers[event.event_type](event)

        measurement_window = HORIZON - WARMUP
        mean_flow_time     = np.mean(self.flow_times) if self.flow_times else 0
        throughput         = len(self.flow_times) / measurement_window
        return mean_flow_time, throughput


if __name__ == "__main__":
    num_agvs       = NUM_AGVS
    agv_capacities = [1, 1]  # one per AGV
    debug_on       = False   # True every event for debugging

    all_flow_times  = []
    all_throughputs = []

    print("=" * 58)
    print(f"  lambda={ARRIVAL_RATE:.5f} req/s | E[S]={L_TIME + (V_MAX + V_MIN)/2 + U_TIME}s")

    for idx_sim in range(NUM_RUNS):  
        print(f"Simulation {idx_sim + 1} out of {NUM_RUNS}") 

        sim = Simulation(num_agvs, agv_capacities)
        mean_ft, throughput = sim.run(debug_on) 

        all_flow_times.append(mean_ft)
        all_throughputs.append(throughput)

        print(f"  Mean flow time : {mean_ft:.3f} s")
        print(f"  Throughput     : {throughput:.6f} req/s")

    mean_ft_avg = np.mean(all_flow_times)
    mean_ft_min = np.min(all_flow_times)
    mean_ft_max = np.max(all_flow_times)
    mean_tp_avg = np.mean(all_throughputs)
    mean_tp_min = np.min(all_throughputs)
    mean_tp_max = np.max(all_throughputs)

    analytical_flowt = 46.46 # from 4.2.1
    analytical_throughput = 1 / 120 

    
    print(f"  Mean flow time : mean={mean_ft_avg:.3f}s  range=[{mean_ft_min:.3f}, {mean_ft_max:.3f}]s")
    print(f"  Analytical E[T]: {analytical_flowt:.3f} s")
    print(f"  Throughput     : mean={mean_tp_avg:.6f}  range=[{mean_tp_min:.6f}, {mean_tp_max:.6f}] req/s")
    print(f"  Analytical throughput   : {analytical_throughput:.6f} req/s")
    rho = ARRIVAL_RATE * (L_TIME + (V_MIN + V_MAX) / 2 + U_TIME) / NUM_AGVS
    print(f"  Utilisation  : {rho*100:.4f}% — warm-up of {WARMUP}s is sufficient")
   