# Domain Intelligence Extension Schemas

## `SectorState`

Required concepts:

- sector entity ID;
- point-in-time constituent set;
- valuation;
- earnings revisions;
- breadth;
- relative strength;
- rate sensitivity;
- commodity dependency;
- policy exposure;
- flow state;
- evidence IDs;
- cutoff time.

## `SupplyChainRelationship`

Required concepts:

- supplier;
- customer;
- facility;
- commodity;
- route;
- geography;
- evidence;
- confidence;
- valid interval;
- substitution alternatives;
- criticality.

## `WeatherObservation`

Required concepts:

- geography;
- variable;
- observation time;
- value;
- unit;
- anomaly;
- source;
- market availability.

## `CropState`

Required concepts:

- crop;
- geography;
- crop stage;
- planted area;
- condition;
- yield expectation;
- weather exposure;
- inventory;
- import/export state.

## `LivestockState`

Required concepts:

- species;
- geography;
- herd size;
- disease state;
- slaughter;
- feed-cost exposure;
- trade restrictions.

## `GeopoliticalState`

Required concepts:

- geography;
- event type;
- actors;
- severity;
- implementation state;
- escalation/de-escalation branches;
- affected trade;
- affected commodities;
- evidence.

## `CommodityState`

Required concepts:

- commodity;
- production;
- consumption;
- inventory;
- imports;
- exports;
- seasonality;
- futures curve;
- weather exposure;
- geopolitical exposure;
- substitution;
- positioning.

## `FlowRecord`

Required concepts:

- disclosure type;
- reporting entity;
- instrument/entity;
- underlying measurement time;
- publication time;
- market availability;
- quantity/value;
- change;
- unknown-hedge flag;
- source;
- reporting lag.
