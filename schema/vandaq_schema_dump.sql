--
-- PostgreSQL database dump
--

-- Dumped from database version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: acquisition_type; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.acquisition_type (
    id integer NOT NULL,
    acquisition_type character varying NOT NULL
);


ALTER TABLE public.acquisition_type OWNER TO postgres;

--
-- Name: acquisition_type_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.acquisition_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.acquisition_type_id_seq OWNER TO postgres;

--
-- Name: acquisition_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.acquisition_type_id_seq OWNED BY public.acquisition_type.id;


--
-- Name: alarm_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.alarm_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.alarm_id_seq OWNER TO postgres;

--
-- Name: alarm; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alarm (
    id bigint DEFAULT nextval('public.alarm_id_seq'::regclass) NOT NULL,
    platform_id integer NOT NULL,
    instrument_id integer NOT NULL,
    sample_time_id bigint NOT NULL,
    alarm_level_id integer NOT NULL,
    alarm_type_id integer NOT NULL,
    parameter_id integer,
    data_impacted boolean NOT NULL,
    message character varying,
    measurement_id bigint
);


ALTER TABLE public.alarm OWNER TO postgres;

--
-- Name: alarm_level; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alarm_level (
    id integer NOT NULL,
    alarm_level character varying NOT NULL
);


ALTER TABLE public.alarm_level OWNER TO postgres;

--
-- Name: alarm_level_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.alarm_level_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.alarm_level_id_seq OWNER TO postgres;

--
-- Name: alarm_level_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.alarm_level_id_seq OWNED BY public.alarm_level.id;


--
-- Name: alarm_type; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alarm_type (
    id integer NOT NULL,
    alarm_type character varying NOT NULL
);


ALTER TABLE public.alarm_type OWNER TO postgres;

--
-- Name: alarm_type_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.alarm_type_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.alarm_type_id_seq OWNER TO postgres;

--
-- Name: alarm_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.alarm_type_id_seq OWNED BY public.alarm_type.id;


--
-- Name: instrument; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.instrument (
    id integer NOT NULL,
    instrument character varying NOT NULL
);


ALTER TABLE public.instrument OWNER TO postgres;

--
-- Name: measurement; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.measurement (
    id bigint NOT NULL,
    acquisition_time_id bigint NOT NULL,
    instrument_time_id bigint,
    sample_time_id bigint NOT NULL,
    instrument_id integer NOT NULL,
    parameter_id integer NOT NULL,
    unit_id integer NOT NULL,
    acquisition_type_id integer NOT NULL,
    value double precision,
    string character varying(100),
    platform_id integer NOT NULL,
    sample_time timestamp without time zone NOT NULL
);


ALTER TABLE public.measurement OWNER TO postgres;

--
-- Name: parameter; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.parameter (
    id integer NOT NULL,
    parameter character varying NOT NULL
);


ALTER TABLE public.parameter OWNER TO postgres;

--
-- Name: platform; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.platform (
    id integer NOT NULL,
    platform character varying NOT NULL
);


ALTER TABLE public.platform OWNER TO postgres;

--
-- Name: time; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public."time" (
    id bigint NOT NULL,
    "time" timestamp without time zone NOT NULL
);


ALTER TABLE public."time" OWNER TO postgres;

--
-- Name: alarms_view; Type: VIEW; Schema: public; Owner: vandaq
--

CREATE VIEW public.alarms_view AS
 SELECT ti."time",
    p.platform,
    i.instrument,
    pa.parameter,
    l.alarm_level,
    t.alarm_type,
    a.data_impacted,
    a.message,
    m.value
   FROM (((((((public.alarm a
     JOIN public.instrument i ON ((a.instrument_id = i.id)))
     JOIN public.parameter pa ON ((a.parameter_id = pa.id)))
     JOIN public.platform p ON ((a.platform_id = p.id)))
     JOIN public.alarm_level l ON ((a.alarm_level_id = l.id)))
     JOIN public.alarm_type t ON ((a.alarm_type_id = t.id)))
     JOIN public."time" ti ON ((a.sample_time_id = ti.id)))
     JOIN public.measurement m ON ((a.measurement_id = m.id)));


ALTER TABLE public.alarms_view OWNER TO vandaq;

--
-- Name: geolocation_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.geolocation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.geolocation_id_seq OWNER TO postgres;

--
-- Name: geolocation; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.geolocation (
    id bigint DEFAULT nextval('public.geolocation_id_seq'::regclass) NOT NULL,
    sample_time_id bigint NOT NULL,
    platform_id integer,
    instrument_id integer NOT NULL,
    latitude double precision,
    longitude double precision
);


ALTER TABLE public.geolocation OWNER TO postgres;

--
-- Name: geolocation_view; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.geolocation_view AS
 SELECT m_lat.sample_time_id,
    m_lat.platform_id,
    m_lat.instrument_id,
    m_lat.value AS latitude,
    m_lon.value AS longitude
   FROM (((((((public.measurement m_lat
     JOIN public.measurement m_lon ON (((m_lat.sample_time_id = m_lon.sample_time_id) AND (m_lat.instrument_id = m_lon.instrument_id) AND (m_lat.platform_id = m_lon.platform_id))))
     JOIN public.platform pl ON ((m_lat.platform_id = pl.id)))
     JOIN public.instrument i ON ((m_lat.instrument_id = i.id)))
     JOIN public.acquisition_type at_lat ON ((m_lat.acquisition_type_id = at_lat.id)))
     JOIN public.acquisition_type at_lon ON ((m_lon.acquisition_type_id = at_lon.id)))
     JOIN public.parameter p_lat ON ((m_lat.parameter_id = p_lat.id)))
     JOIN public.parameter p_lon ON ((m_lon.parameter_id = p_lon.id)))
  WHERE (((at_lat.acquisition_type)::text = 'GPS'::text) AND ((at_lon.acquisition_type)::text = 'GPS'::text) AND ((p_lat.parameter)::text = 'latitude'::text) AND ((p_lon.parameter)::text = 'longitude'::text));


ALTER TABLE public.geolocation_view OWNER TO postgres;

--
-- Name: instrument_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.instrument_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.instrument_id_seq OWNER TO postgres;

--
-- Name: instrument_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.instrument_id_seq OWNED BY public.instrument.id;


--
-- Name: instrument_measurements; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.instrument_measurements (
    id integer NOT NULL,
    instrument_id integer NOT NULL,
    parameter_id integer NOT NULL,
    unit_id integer NOT NULL,
    acquisition_type_id integer NOT NULL,
    platform_id integer
);


ALTER TABLE public.instrument_measurements OWNER TO postgres;

--
-- Name: instrument_measurements_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.instrument_measurements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.instrument_measurements_id_seq OWNER TO postgres;

--
-- Name: instrument_measurements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.instrument_measurements_id_seq OWNED BY public.instrument_measurements.id;


--
-- Name: unit; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.unit (
    id integer NOT NULL,
    unit character varying NOT NULL
);


ALTER TABLE public.unit OWNER TO postgres;

--
-- Name: measurement_expanded; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.measurement_expanded AS
 SELECT m.id AS measurement_id,
    t1."time" AS acquisition_time,
    t2."time" AS instrument_time,
    t3."time" AS sample_time,
    i.instrument AS instrument_name,
    p.parameter AS parameter_name,
    u.unit AS unit_name,
    at.acquisition_type AS acquisition_type_name,
    m.value,
    m.string,
    plat.platform AS platform_name
   FROM ((((((((public.measurement m
     LEFT JOIN public."time" t1 ON ((m.acquisition_time_id = t1.id)))
     LEFT JOIN public."time" t2 ON ((m.instrument_time_id = t2.id)))
     LEFT JOIN public."time" t3 ON ((m.sample_time_id = t3.id)))
     LEFT JOIN public.instrument i ON ((m.instrument_id = i.id)))
     LEFT JOIN public.parameter p ON ((m.parameter_id = p.id)))
     LEFT JOIN public.unit u ON ((m.unit_id = u.id)))
     LEFT JOIN public.acquisition_type at ON ((m.acquisition_type_id = at.id)))
     LEFT JOIN public.platform plat ON ((m.platform_id = plat.id)))
  ORDER BY t3."time";


ALTER TABLE public.measurement_expanded OWNER TO postgres;

--
-- Name: measurement_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.measurement_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.measurement_id_seq OWNER TO postgres;

--
-- Name: measurement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.measurement_id_seq OWNED BY public.measurement.id;


--
-- Name: parameter_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.parameter_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.parameter_id_seq OWNER TO postgres;

--
-- Name: parameter_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.parameter_id_seq OWNED BY public.parameter.id;


--
-- Name: platform_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.platform_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.platform_id_seq OWNER TO postgres;

--
-- Name: platform_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.platform_id_seq OWNED BY public.platform.id;


--
-- Name: time_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.time_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.time_id_seq OWNER TO postgres;

--
-- Name: time_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.time_id_seq OWNED BY public."time".id;


--
-- Name: unit_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.unit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.unit_id_seq OWNER TO postgres;

--
-- Name: unit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.unit_id_seq OWNED BY public.unit.id;


--
-- Name: acquisition_type id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.acquisition_type ALTER COLUMN id SET DEFAULT nextval('public.acquisition_type_id_seq'::regclass);


--
-- Name: alarm_level id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm_level ALTER COLUMN id SET DEFAULT nextval('public.alarm_level_id_seq'::regclass);


--
-- Name: alarm_type id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm_type ALTER COLUMN id SET DEFAULT nextval('public.alarm_type_id_seq'::regclass);


--
-- Name: instrument id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument ALTER COLUMN id SET DEFAULT nextval('public.instrument_id_seq'::regclass);


--
-- Name: instrument_measurements id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument_measurements ALTER COLUMN id SET DEFAULT nextval('public.instrument_measurements_id_seq'::regclass);


--
-- Name: measurement id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement ALTER COLUMN id SET DEFAULT nextval('public.measurement_id_seq'::regclass);


--
-- Name: parameter id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.parameter ALTER COLUMN id SET DEFAULT nextval('public.parameter_id_seq'::regclass);


--
-- Name: platform id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.platform ALTER COLUMN id SET DEFAULT nextval('public.platform_id_seq'::regclass);


--
-- Name: time id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public."time" ALTER COLUMN id SET DEFAULT nextval('public.time_id_seq'::regclass);


--
-- Name: unit id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.unit ALTER COLUMN id SET DEFAULT nextval('public.unit_id_seq'::regclass);


--
-- Name: acquisition_type acquisition_type_aquisition_type_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.acquisition_type
    ADD CONSTRAINT acquisition_type_aquisition_type_key UNIQUE (acquisition_type);


--
-- Name: acquisition_type acquisition_type_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.acquisition_type
    ADD CONSTRAINT acquisition_type_pkey PRIMARY KEY (id);


--
-- Name: alarm_level alarm_level_alarm_level_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm_level
    ADD CONSTRAINT alarm_level_alarm_level_key UNIQUE (alarm_level);


--
-- Name: alarm_level alarm_level_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm_level
    ADD CONSTRAINT alarm_level_pkey PRIMARY KEY (id);


--
-- Name: alarm alarm_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm
    ADD CONSTRAINT alarm_pkey PRIMARY KEY (id);


--
-- Name: alarm_type alarm_type_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm_type
    ADD CONSTRAINT alarm_type_pkey PRIMARY KEY (id);


--
-- Name: alarm_type alarm_type_unique; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm_type
    ADD CONSTRAINT alarm_type_unique UNIQUE (alarm_type);


--
-- Name: geolocation geolocation_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.geolocation
    ADD CONSTRAINT geolocation_pkey PRIMARY KEY (id);


--
-- Name: instrument instrument_instrument_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument
    ADD CONSTRAINT instrument_instrument_key UNIQUE (instrument);


--
-- Name: instrument_measurements instrument_measurements_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_pkey PRIMARY KEY (id);


--
-- Name: instrument instrument_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument
    ADD CONSTRAINT instrument_pkey PRIMARY KEY (id);


--
-- Name: measurement measurement_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_pkey PRIMARY KEY (id);


--
-- Name: parameter parameter_parameter_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.parameter
    ADD CONSTRAINT parameter_parameter_key UNIQUE (parameter);


--
-- Name: parameter parameter_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.parameter
    ADD CONSTRAINT parameter_pkey PRIMARY KEY (id);


--
-- Name: platform platform_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.platform
    ADD CONSTRAINT platform_pkey PRIMARY KEY (id);


--
-- Name: time time_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public."time"
    ADD CONSTRAINT time_pkey PRIMARY KEY (id);


--
-- Name: time time_time_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public."time"
    ADD CONSTRAINT time_time_key UNIQUE ("time");


--
-- Name: unit unit_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.unit
    ADD CONSTRAINT unit_pkey PRIMARY KEY (id);


--
-- Name: unit unit_unit_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.unit
    ADD CONSTRAINT unit_unit_key UNIQUE (unit);


--
-- Name: instrument_measurements uq_instrument_measurements; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT uq_instrument_measurements UNIQUE (instrument_id, parameter_id, unit_id, acquisition_type_id);


--
-- Name: fki_instrument_measurements_platform_id_fkey; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX fki_instrument_measurements_platform_id_fkey ON public.instrument_measurements USING btree (platform_id);


--
-- Name: fki_measurement_platform_id_fkey; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX fki_measurement_platform_id_fkey ON public.measurement USING btree (platform_id);


--
-- Name: idx_acquisition_type_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_acquisition_type_id ON public.acquisition_type USING btree (id);


--
-- Name: idx_alarm_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alarm_id ON public.alarm USING btree (id) WITH (deduplicate_items='true');


--
-- Name: idx_alarm_level_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alarm_level_id ON public.alarm_level USING btree (id) WITH (deduplicate_items='false');


--
-- Name: idx_alarm_measurement_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alarm_measurement_id ON public.alarm USING btree (measurement_id) WITH (deduplicate_items='true');


--
-- Name: idx_alarm_sample_time_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alarm_sample_time_id ON public.alarm USING btree (sample_time_id) WITH (deduplicate_items='false');


--
-- Name: idx_alarm_type_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alarm_type_id ON public.alarm_type USING btree (id) WITH (deduplicate_items='false');


--
-- Name: idx_geolocation_sample_time_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_geolocation_sample_time_id ON public.geolocation USING btree (sample_time_id) WITH (deduplicate_items='true');


--
-- Name: idx_geolocation_time_platform_instrument_ids; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_geolocation_time_platform_instrument_ids ON public.geolocation USING btree (sample_time_id, platform_id, instrument_id) WITH (deduplicate_items='true');


--
-- Name: idx_instrument_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_instrument_id ON public.instrument USING btree (id);


--
-- Name: idx_measurement_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_measurement_id ON public.measurement USING btree (id) WITH (deduplicate_items='true');


--
-- Name: idx_measurement_sample_id_brin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_measurement_sample_id_brin ON public.measurement USING brin (sample_time_id) WITH (autosummarize='false');


--
-- Name: idx_measurement_sample_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_measurement_sample_time ON public.measurement USING brin (sample_time) WITH (autosummarize='false');


--
-- Name: idx_parameter_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_parameter_id ON public.parameter USING btree (id);


--
-- Name: idx_platform_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_platform_id ON public.platform USING btree (id) WITH (deduplicate_items='true');


--
-- Name: idx_sample_time_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_sample_time_id ON public.measurement USING btree (sample_time_id) WITH (deduplicate_items='true');


--
-- Name: idx_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_time ON public."time" USING btree ("time") WITH (deduplicate_items='true');


--
-- Name: idx_time_brin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_time_brin ON public."time" USING brin ("time") WITH (autosummarize='false');


--
-- Name: idx_time_id_brin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_time_id_brin ON public."time" USING brin (id) WITH (autosummarize='false');


--
-- Name: idx_unit_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_unit_id ON public.unit USING btree (id);


--
-- Name: alarm acq_time_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm
    ADD CONSTRAINT acq_time_fk FOREIGN KEY (sample_time_id) REFERENCES public."time"(id);


--
-- Name: alarm alarm_severity_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm
    ADD CONSTRAINT alarm_severity_id_fk FOREIGN KEY (alarm_level_id) REFERENCES public.alarm_level(id);


--
-- Name: alarm alarm_type_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm
    ADD CONSTRAINT alarm_type_id_fk FOREIGN KEY (alarm_type_id) REFERENCES public.alarm_type(id);


--
-- Name: geolocation geolocation_instrument_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.geolocation
    ADD CONSTRAINT geolocation_instrument_id_fkey FOREIGN KEY (instrument_id) REFERENCES public.instrument(id);


--
-- Name: geolocation geolocation_platform_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.geolocation
    ADD CONSTRAINT geolocation_platform_id_fkey FOREIGN KEY (platform_id) REFERENCES public.platform(id);


--
-- Name: geolocation geolocation_sample_time_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.geolocation
    ADD CONSTRAINT geolocation_sample_time_id_fkey FOREIGN KEY (sample_time_id) REFERENCES public."time"(id);


--
-- Name: alarm instrument_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm
    ADD CONSTRAINT instrument_id_fk FOREIGN KEY (instrument_id) REFERENCES public.instrument(id);


--
-- Name: instrument_measurements instrument_measurements_acquisition_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_acquisition_type_id_fkey FOREIGN KEY (acquisition_type_id) REFERENCES public.acquisition_type(id);


--
-- Name: instrument_measurements instrument_measurements_instrument_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_instrument_id_fkey FOREIGN KEY (instrument_id) REFERENCES public.instrument(id);


--
-- Name: instrument_measurements instrument_measurements_parameter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_parameter_id_fkey FOREIGN KEY (parameter_id) REFERENCES public.parameter(id);


--
-- Name: instrument_measurements instrument_measurements_platform_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_platform_id_fkey FOREIGN KEY (platform_id) REFERENCES public.platform(id);


--
-- Name: instrument_measurements instrument_measurements_unit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES public.unit(id);


--
-- Name: measurement measurement_acquisition_time_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_acquisition_time_id_fkey FOREIGN KEY (acquisition_time_id) REFERENCES public."time"(id);


--
-- Name: measurement measurement_acquisition_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_acquisition_type_id_fkey FOREIGN KEY (acquisition_type_id) REFERENCES public.acquisition_type(id);


--
-- Name: alarm measurement_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm
    ADD CONSTRAINT measurement_id_fk FOREIGN KEY (measurement_id) REFERENCES public.measurement(id) NOT VALID;


--
-- Name: measurement measurement_instrument_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_instrument_id_fkey FOREIGN KEY (instrument_id) REFERENCES public.instrument(id);


--
-- Name: measurement measurement_instrument_time_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_instrument_time_id_fkey FOREIGN KEY (instrument_time_id) REFERENCES public."time"(id);


--
-- Name: measurement measurement_parameter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_parameter_id_fkey FOREIGN KEY (parameter_id) REFERENCES public.parameter(id);


--
-- Name: measurement measurement_platform_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_platform_id_fkey FOREIGN KEY (platform_id) REFERENCES public.platform(id);


--
-- Name: measurement measurement_sample_time_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_sample_time_id_fkey FOREIGN KEY (sample_time_id) REFERENCES public."time"(id);


--
-- Name: measurement measurement_unit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES public.unit(id);


--
-- Name: alarm parameter_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm
    ADD CONSTRAINT parameter_id_fk FOREIGN KEY (parameter_id) REFERENCES public.parameter(id);


--
-- Name: alarm platform_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarm
    ADD CONSTRAINT platform_id_fk FOREIGN KEY (platform_id) REFERENCES public.platform(id);


--
-- PostgreSQL database dump complete
--

--
-- PostgreSQL database dump
--

-- Dumped from database version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: alarm_level; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.alarm_level (id, alarm_level) FROM stdin;
1	warning
2	alarm
\.


--
-- Name: alarm_level_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.alarm_level_id_seq', 2, true);


--
-- PostgreSQL database dump complete
--

