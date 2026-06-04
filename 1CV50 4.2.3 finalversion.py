import heapq        # used to manage the future event list (always gives smallest time first)
import random       # used to generate random numbers (arrivals, sources)
import numpy as np  # used for mean, min, max calculations

# TRAVEL TIME TABLE (Table 2 from assignment decription)
# TRAVEL_TIMES[(from_node, to_node)] = travel time in seconds
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

ARRIVAL_RATE = 1 / 50   # one request every 50 seconds on average (Poisson)
L_TIME       = 3        # loading time 
U_TIME       = 3        # unloading time
HORIZON      = 300000   # total simulation time in seconds
WARMUP       = 50000    # first 50000 seconds are not recorded, avoiding bias (warm-up)
NUM_RUNS     = 10       # indicates how many times we repeat each simulation

# source nodes sampled uniformly at random for each request
SOURCE_NODES = [0, 10, 20, 30, 40, 50, 60]

# destination is always the next station in sequence as indicated in the case description
NEXT_STATION = {0: 10, 10: 20, 20: 30, 30: 40, 40: 50, 50: 60, 60: 70}


# Rules from lecture slides SDF-FIFO, SDF-LRO, SDF-SST
# SDF = Shortest Distance First (but firstly, minimize empty travel)
# If equal, secondary criterion is different per rule
# Our 4 rules for 4.2.3
# Rule 0: FCFS 
# serve request that arrived earliest, do notthink about distances
# Rule 1: SDF-FIFO 
# pick request with SHORTEST empty travel (calculating drom AGV's current position to source)
# if equal distance, pick the one that arrived first (FIFO)
# Rule 2: SDF-STT 
#  pick request with shortest empty travel (from agv s current position to the source node)
#  if equal, pick the one with shortest loaded travel (source to destination)
#                (adapting SST = Shortest Service Time → here = shortest loaded trip)
# Rule 3: SDF-LWT (longest waiting time)
# pick request with empty travel
# if equal distance, pick the request that has been waiting LONGEST


RULE_NAMES = {
    0: "FCFS",
    1: "SDF-FIFO",
    2: "SDF-STT",
    3: "SDF-LWT",
}



class Event(object): #represents events happenning a t a time

    # event types
    ENTITY_ARRIVAL  = 0   # a new transport request arrived
    ENTITY_COMPLETE = 1   # an AGV finished a request

    EVENT_TO_STR = {0: "ARRIVAL", 1: "COMPLETE"}

    def __init__(self, event_type, time, entity=None, resource_id=None):
        self.event_type  = event_type    # what kind of event (0 or 1)
        self.time        = time          # when does this event happen
        self.entity      = entity        # which request is involved
        self.resource_id = resource_id   # which AGV is involved

    def __lt__(self, other):
        # tells Python how to sort events in the heap
        # earlier is being served 
        # if same time: lower entity (index) id goes first 
        if self.time == other.time:
            if self.entity and other.entity:
                return self.entity.id < other.entity.id
        return self.time < other.time


# represents one AGV
class Resource(object):

    def __init__(self, resource_id, capacity):
        self.id               = resource_id  # AGV id: 0 or 1
        self.capacity         = capacity     # max requests at once is 1per AGV
        self.current_entities = []           # list of requests AGV is currently serving
        self.queue            = []           # is not used as we use shared queue
        self.current_position = 90           # AGV starts at parking node 90
        self.available_at     = 0            # the time when AGV becomes free (starts at 0)
        self.busy_time        = 0            # total time AGV worked to compute utilization)

    def seize(self, entity):
        # AGV takes a request: now it is busy
        self.current_entities.append(entity)
        return self.id

    def release(self, entity_id):
        # AGV finishes the task: remove the request from its list
        self.current_entities = [
            e for e in self.current_entities if e.id != entity_id
        ]

    def is_available(self):
        # returns True if AGV is free of request
        return len(self.current_entities) < self.capacity


# entity class represents one request

class Entity(object):

    def __init__(self, entity_id, source, dest):
        self.id                 = entity_id  # unique request number
        self.source             = source     # pickup node
        self.dest               = dest       # drop node is destination
        self.arrival_time       = None       # when request entered the queue
        self.start_service_time = None       # when AGV started this request
        self.departure_time     = None       # when AGV finished
        self.resource_id        = None       # which AGV served this request



class Simulation(object):
    
    #Requests arrive according to a Poisson process: 50s and lambda is 1/50 req per second
    #Source is random from [00,10,20,30,40,50,60] o to 10, 10 to 20, 20 to 30.. 50 to 60
    #2 AGVs start at node 90 (parking lot)
    #Our rules: 
    #rule 0: FCFS
    #rule 1: SDF- FIFO (shortest distance, then earliest arrival time)
    #rule 2: SDF-STT   (shortest distance first, then shortest loaded travel)
    #rule 3: SDF-LWT   (shortest distance first, then longest waiting time)
    

    def __init__(self, num_agvs, agv_capacities, rule):
        self.now            = 0     # simulation clock starts at 0
        self.events         = []    # future event list (used heap)
        self.queue          = []    # requests in the queue
        self.completed_jobs = []    # requests tjhat are completed by a AGV
        self.job_counters   = 0     # to give each request a unique identifier id
        self.warmup_done    = False # becomes True after warmup period 
        self.rule           = rule  # which dispatching rule to use (0,1,2,3)

        # create the 2 AGVs
        self.machines = [
            Resource(i, capacity=agv_capacities[i]) for i in range(num_agvs)
        ]

        # statistics are recorded after warmyp period
        self.flow_times    = []  # total time each request spent in system
        self.waiting_times = []  # the time each request waited

    def add_event(self, event):
        # heappush keeps the list sorted as the smallest time is always at front
        heapq.heappush(self.events, event)
    def get_next_event(self):
        # heappop removes and returns the event with smallest time
        return heapq.heappop(self.events) if self.events else None

    def get_free_agv(self):
        # return the first AGV that is free
        for agv in self.machines:
            if agv.is_available():
                return agv
        return None  # if both AGVs are busy

    def get_inter_arrival_time(self):
        # exponential distribution because Poisson arrivals, mean = 50s
        return random.expovariate(ARRIVAL_RATE)


    def compute_completion_time(self, agv, request):
        #AGV travels without load from current position to source
        empty_travel = TRAVEL_TIMES[(agv.current_position, request.source)]

        #AGV arrives at source
        arrive_at_source = self.now + empty_travel

        #loading starts immediately after arriving
        load_start = arrive_at_source

        #AGV travels with the load from source to destination
        loaded_travel = TRAVEL_TIMES[(request.source, request.dest)]

        #total time
        completion_time = load_start + L_TIME + loaded_travel + U_TIME

        return completion_time

    # which request will AGV handle?
    def select_request(self, agv):
        # if there is no request in the queue, return nothing
        if not self.queue:
            return None

        # 0: FCFS 
        # serve the request that arrived first and do not count distances
        if self.rule == 0:
            return self.queue.pop(0)

        #1: SDF-FIFO
        #First, shortest empty travel ( from AGVs current position to the source node)
        # if two requests are equally close,
        # serve the one that arrived first: FIFO = lower arrival_time
        elif self.rule == 1:
            best_index = 0

            for i in range(1, len(self.queue)):
                # compute empty travel to each request's source
                dist_best = TRAVEL_TIMES[(agv.current_position,
                                          self.queue[best_index].source)]
                dist_i    = TRAVEL_TIMES[(agv.current_position,
                                          self.queue[i].source)]

                if dist_i < dist_best:
                    # the closer one is better logic
                    best_index = i
                elif dist_i == dist_best:
                    #applying FIFO earlier arrival
                    if self.queue[i].arrival_time < self.queue[best_index].arrival_time:
                        best_index = i

            return self.queue.pop(best_index)

        #2: SDF-STT (shortest service tme)
        # First, shortest empty travel (AGV current position to source)
        # if they are equally close, pick request with shortest loaded travel
        #which is the destination from source to destinatione
        elif self.rule == 2:
            best_index = 0

            for i in range(1, len(self.queue)):
                dist_best = TRAVEL_TIMES[(agv.current_position,
                                          self.queue[best_index].source)]
                dist_i    = TRAVEL_TIMES[(agv.current_position,
                                          self.queue[i].source)]

                if dist_i < dist_best:
                    # the lower the distance, the better
                    best_index = i
                elif dist_i == dist_best:
                    # if they are equal, pick shorter loaded travel (shorter total service)
                    loaded_best = TRAVEL_TIMES[(self.queue[best_index].source,
                                                self.queue[best_index].dest)]
                    loaded_i    = TRAVEL_TIMES[(self.queue[i].source,
                                                self.queue[i].dest)]
                    if loaded_i < loaded_best:
                        best_index = i

            return self.queue.pop(best_index)

        # 3: SDF-LWT=
        #First, shortest empty travel
        #if equally close, pick request that has waited longest
        #  smallest arrival_time = has been waiting the most
        elif self.rule == 3:
            best_index = 0

            for i in range(1, len(self.queue)):
                dist_best = TRAVEL_TIMES[(agv.current_position,
                                          self.queue[best_index].source)]
                dist_i    = TRAVEL_TIMES[(agv.current_position,
                                          self.queue[i].source)]

                if dist_i < dist_best:
                    # closer is better
                    best_index = i
                elif dist_i == dist_best:
                    # if equal, pick the one that has been waiting longest
                    if self.queue[i].arrival_time < self.queue[best_index].arrival_time:
                        best_index = i

            return self.queue.pop(best_index)

        #FCFS
        return self.queue.pop(0)

  
    def setup(self):
        # creating the first request
        first_arrival_time = self.get_inter_arrival_time()
        source             = random.choice(SOURCE_NODES)
        dest               = NEXT_STATION[source]
        first_request      = Entity(self.job_counters, source, dest)

        # record it on the heap as an arrival event
        self.add_event(Event(Event.ENTITY_ARRIVAL, first_arrival_time, first_request))

    def process_arrival_event(self, event):
        # a new transport request just arrived
        request              = event.entity
        request.arrival_time = self.now   # record when it arrived

        # add it to the waiting queue
        self.queue.append(request)

        # schedule the NEXT arrival
        self.job_counters      += 1
        next_time               = self.now + self.get_inter_arrival_time()
        next_source             = random.choice(SOURCE_NODES)
        next_dest               = NEXT_STATION[next_source]
        next_request            = Entity(self.job_counters, next_source, next_dest)
        self.add_event(Event(Event.ENTITY_ARRIVAL, next_time, next_request))

        # assigning a free AGV
        self.request_machines()

    def process_departure_event(self, event):
        # When an AGV finished delivering a request
        request                = event.entity
        agv_id                 = event.resource_id
        request.departure_time = self.now  # record when it finished

        # updating agvs location: destination 
        self.machines[agv_id].current_position = request.dest
        self.machines[agv_id].available_at     = self.now

        # collect statistics ONLY after warmup period
        if self.warmup_done:
            # flow time  = waiting + served
            flow_time    = request.departure_time - request.arrival_time
            # waiting time = time spent in queue before AGV arrived
            waiting_time = request.start_service_time - request.arrival_time
            self.flow_times.append(flow_time)
            self.waiting_times.append(waiting_time)

            #utilization calculation
            service_duration = request.departure_time - request.start_service_time
            self.machines[agv_id].busy_time += service_duration

        # free the AGV
        self.machines[agv_id].release(request.id)
        self.completed_jobs.append(request)

        # check if any requests remained
        self.request_machines()

    # dispatching
    def request_machines(self):
        # keep assigning requests to AGVs as long as:
        # - there are requests waiting in the queue AND
        # - there is at least one free AGV
        while self.queue and self.get_free_agv() is not None:
            agv = self.get_free_agv()  # get a free AGV

            # use the dispatching rule to pick which request this AGV takes
            request = self.select_request(agv)
            if request is None:
                break

            # assign the request to this AGV
            agv_id                     = agv.seize(request)
            request.start_service_time = self.now   # record when service started
            request.resource_id        = agv_id     # record which AGV served it

            # calculate when this AGV will finish
            completion_time  = self.compute_completion_time(agv, request)
            agv.available_at = completion_time  # AGV won't be free until then

            # schedule the completion event
            self.add_event(Event(Event.ENTITY_COMPLETE,
                                 completion_time,
                                 request,
                                 resource_id=agv_id))

    def run(self): # running simulation
        self.setup()  # schedule first arrival

        # map event types to their functions
        event_handlers = {
            Event.ENTITY_ARRIVAL:  self.process_arrival_event,
            Event.ENTITY_COMPLETE: self.process_departure_event,
        }

        # processing events
        while self.events:
            event = self.get_next_event()  # getting the earliest event
            if not event:
                break
            if event.time > HORIZON:  # stop at horizon
                break

            self.now = event.time  

            # checking if the warmup period has ended
            if not self.warmup_done and self.now >= WARMUP:
                self.warmup_done = True    # start rrecording ig the warmup period passed
                for agv in self.machines:
                    agv.busy_time = 0  #reset busy time before warmup 

            # match the right handler for the event type
            event_handlers[event.event_type](event)

        # calculation
        measurement_window = HORIZON - WARMUP  # 250000 seconds

        # mean flow time: average time a request spent in the system
        mean_flow_time = np.mean(self.flow_times) if self.flow_times else 0

        # mean waiting time
        mean_waiting_time = np.mean(self.waiting_times) if self.waiting_times else 0

        # throughput
        throughput = len(self.flow_times) / measurement_window

        # AGV utilization
        total_busy_time = sum(agv.busy_time for agv in self.machines)
        utilization     = total_busy_time / (len(self.machines) * measurement_window)

        return mean_flow_time, mean_waiting_time, throughput, utilization

# run rules, 10 times each

if __name__ == "__main__":

    num_agvs       = 2
    agv_capacities = [1, 1]   # each AGV serves one request at a time

    # dictionary to store all results
    # structure: results[rule_id] = list of (flow, wait, throughput, utilization)
    results = {0: [], 1: [], 2: [], 3: []}

    print("  Exercise 4.2.3 — AGV Dispatching Rules (Lecture Style)")
   
    print(f"  λ=1/50 req/s | AGVs=2 | Horizon={HORIZON}s | Warmup={WARMUP}s")


    # loop each rule
    for rule_id in [0, 1, 2, 3]:
        print(f"\nRule {rule_id}: {RULE_NAMES[rule_id]}")
       
        # run 10 independent replications
        for run in range(NUM_RUNS):
            # set random seed so results are reproducible
            random.seed(rule_id * 100 + run)

            # create a fresh simulation with this rule
            sim = Simulation(num_agvs, agv_capacities, rule=rule_id)

            # run and collect metrics
            flow, wait, tput, util = sim.run()

            # store results
            results[rule_id].append((flow, wait, tput, util))

            print(f"  Run {run+1:>2}: "
                  f"flow={flow:.2f}s  "
                  f"wait={wait:.2f}s  "
                  f"throughput={tput:.6f}  "
                  f"utilization={util*100:.1f}%")

    
    print(f"  {'Rule':<30} {'Flow(s)':>9} {'Wait(s)':>9} "
          f"{'Tput':>10} {'Util%':>7}")

    for rule_id in [0, 1, 2, 3]:
        all_flows = [r[0] for r in results[rule_id]]
        all_waits = [r[1] for r in results[rule_id]]
        all_tputs = [r[2] for r in results[rule_id]]
        all_utils = [r[3] for r in results[rule_id]]

        # compute means and standard deviations
        avg_flow = np.mean(all_flows)
        std_flow = np.std(all_flows)
        avg_wait = np.mean(all_waits)
        avg_tput = np.mean(all_tputs)
        avg_util = np.mean(all_utils)

        print(f"  {RULE_NAMES[rule_id]:<30} "
              f"{avg_flow:>9.3f} "
              f"{avg_wait:>9.3f} "
              f"{avg_tput:>10.6f} "
              f"{avg_util*100:>6.1f}%")

        # print range and std
        print(f"  {'':30} "
              f"range=[{np.min(all_flows):.2f}, {np.max(all_flows):.2f}]s  "
              f"std={std_flow:.3f}s")

    