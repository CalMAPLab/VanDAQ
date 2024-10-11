--
-- PostgreSQL database dump
--

-- Dumped from database version 14.13 (Ubuntu 14.13-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.13 (Ubuntu 14.13-0ubuntu0.22.04.1)

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
-- Name: acquisition_type; Type: TABLE; Schema: public; Owner: vandaq
--

CREATE TABLE public.acquisition_type (
    id integer NOT NULL,
    acquisition_type character varying NOT NULL
);


ALTER TABLE public.acquisition_type OWNER TO vandaq;

--
-- Name: acquisition_type_id_seq; Type: SEQUENCE; Schema: public; Owner: vandaq
--

CREATE SEQUENCE public.acquisition_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.acquisition_type_id_seq OWNER TO vandaq;

--
-- Name: acquisition_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: vandaq
--

ALTER SEQUENCE public.acquisition_type_id_seq OWNED BY public.acquisition_type.id;


--
-- Name: instrument; Type: TABLE; Schema: public; Owner: vandaq
--

CREATE TABLE public.instrument (
    id integer NOT NULL,
    instrument character varying NOT NULL
);


ALTER TABLE public.instrument OWNER TO vandaq;

--
-- Name: instrument_id_seq; Type: SEQUENCE; Schema: public; Owner: vandaq
--

CREATE SEQUENCE public.instrument_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.instrument_id_seq OWNER TO vandaq;

--
-- Name: instrument_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: vandaq
--

ALTER SEQUENCE public.instrument_id_seq OWNED BY public.instrument.id;


--
-- Name: instrument_measurements; Type: TABLE; Schema: public; Owner: vandaq
--

CREATE TABLE public.instrument_measurements (
    id integer NOT NULL,
    instrument_id integer NOT NULL,
    parameter_id integer NOT NULL,
    unit_id integer NOT NULL,
    acquisition_type_id integer NOT NULL,
    platform_id integer
);


ALTER TABLE public.instrument_measurements OWNER TO vandaq;

--
-- Name: instrument_measurements_id_seq; Type: SEQUENCE; Schema: public; Owner: vandaq
--

CREATE SEQUENCE public.instrument_measurements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.instrument_measurements_id_seq OWNER TO vandaq;

--
-- Name: instrument_measurements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: vandaq
--

ALTER SEQUENCE public.instrument_measurements_id_seq OWNED BY public.instrument_measurements.id;


--
-- Name: measurement; Type: TABLE; Schema: public; Owner: vandaq
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
    value double precision NOT NULL,
    string character varying(100),
    platform_id integer
);


ALTER TABLE public.measurement OWNER TO vandaq;

--
-- Name: measurement_id_seq; Type: SEQUENCE; Schema: public; Owner: vandaq
--

CREATE SEQUENCE public.measurement_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.measurement_id_seq OWNER TO vandaq;

--
-- Name: measurement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: vandaq
--

ALTER SEQUENCE public.measurement_id_seq OWNED BY public.measurement.id;


--
-- Name: parameter; Type: TABLE; Schema: public; Owner: vandaq
--

CREATE TABLE public.parameter (
    id integer NOT NULL,
    parameter character varying NOT NULL
);


ALTER TABLE public.parameter OWNER TO vandaq;

--
-- Name: parameter_id_seq; Type: SEQUENCE; Schema: public; Owner: vandaq
--

CREATE SEQUENCE public.parameter_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.parameter_id_seq OWNER TO vandaq;

--
-- Name: parameter_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: vandaq
--

ALTER SEQUENCE public.parameter_id_seq OWNED BY public.parameter.id;


--
-- Name: platform; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.platform (
    id integer NOT NULL,
    platform character varying NOT NULL
);


ALTER TABLE public.platform OWNER TO postgres;

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
-- Name: time; Type: TABLE; Schema: public; Owner: vandaq
--

CREATE TABLE public."time" (
    id bigint NOT NULL,
    "time" timestamp without time zone NOT NULL
);


ALTER TABLE public."time" OWNER TO vandaq;

--
-- Name: time_id_seq; Type: SEQUENCE; Schema: public; Owner: vandaq
--

CREATE SEQUENCE public.time_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.time_id_seq OWNER TO vandaq;

--
-- Name: time_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: vandaq
--

ALTER SEQUENCE public.time_id_seq OWNED BY public."time".id;


--
-- Name: unit; Type: TABLE; Schema: public; Owner: vandaq
--

CREATE TABLE public.unit (
    id integer NOT NULL,
    unit character varying NOT NULL
);


ALTER TABLE public.unit OWNER TO vandaq;

--
-- Name: unit_id_seq; Type: SEQUENCE; Schema: public; Owner: vandaq
--

CREATE SEQUENCE public.unit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.unit_id_seq OWNER TO vandaq;

--
-- Name: unit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: vandaq
--

ALTER SEQUENCE public.unit_id_seq OWNED BY public.unit.id;


--
-- Name: acquisition_type id; Type: DEFAULT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.acquisition_type ALTER COLUMN id SET DEFAULT nextval('public.acquisition_type_id_seq'::regclass);


--
-- Name: instrument id; Type: DEFAULT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument ALTER COLUMN id SET DEFAULT nextval('public.instrument_id_seq'::regclass);


--
-- Name: instrument_measurements id; Type: DEFAULT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument_measurements ALTER COLUMN id SET DEFAULT nextval('public.instrument_measurements_id_seq'::regclass);


--
-- Name: measurement id; Type: DEFAULT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement ALTER COLUMN id SET DEFAULT nextval('public.measurement_id_seq'::regclass);


--
-- Name: parameter id; Type: DEFAULT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.parameter ALTER COLUMN id SET DEFAULT nextval('public.parameter_id_seq'::regclass);


--
-- Name: platform id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.platform ALTER COLUMN id SET DEFAULT nextval('public.platform_id_seq'::regclass);


--
-- Name: time id; Type: DEFAULT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public."time" ALTER COLUMN id SET DEFAULT nextval('public.time_id_seq'::regclass);


--
-- Name: unit id; Type: DEFAULT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.unit ALTER COLUMN id SET DEFAULT nextval('public.unit_id_seq'::regclass);


--
-- Name: acquisition_type acquisition_type_aquisition_type_key; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.acquisition_type
    ADD CONSTRAINT acquisition_type_aquisition_type_key UNIQUE (acquisition_type);


--
-- Name: acquisition_type acquisition_type_pkey; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.acquisition_type
    ADD CONSTRAINT acquisition_type_pkey PRIMARY KEY (id);


--
-- Name: instrument instrument_instrument_key; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument
    ADD CONSTRAINT instrument_instrument_key UNIQUE (instrument);


--
-- Name: instrument_measurements instrument_measurements_pkey; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_pkey PRIMARY KEY (id);


--
-- Name: instrument instrument_pkey; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument
    ADD CONSTRAINT instrument_pkey PRIMARY KEY (id);


--
-- Name: measurement measurement_pkey; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_pkey PRIMARY KEY (id);


--
-- Name: parameter parameter_parameter_key; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.parameter
    ADD CONSTRAINT parameter_parameter_key UNIQUE (parameter);


--
-- Name: parameter parameter_pkey; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.parameter
    ADD CONSTRAINT parameter_pkey PRIMARY KEY (id);


--
-- Name: platform platform_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.platform
    ADD CONSTRAINT platform_pkey PRIMARY KEY (id);


--
-- Name: time time_pkey; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public."time"
    ADD CONSTRAINT time_pkey PRIMARY KEY (id);


--
-- Name: time time_time_key; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public."time"
    ADD CONSTRAINT time_time_key UNIQUE ("time");


--
-- Name: unit unit_pkey; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.unit
    ADD CONSTRAINT unit_pkey PRIMARY KEY (id);


--
-- Name: unit unit_unit_key; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.unit
    ADD CONSTRAINT unit_unit_key UNIQUE (unit);


--
-- Name: instrument_measurements uq_instrument_measurements; Type: CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT uq_instrument_measurements UNIQUE (instrument_id, parameter_id, unit_id, acquisition_type_id);


--
-- Name: fki_instrument_measurements_platform_id_fkey; Type: INDEX; Schema: public; Owner: vandaq
--

CREATE INDEX fki_instrument_measurements_platform_id_fkey ON public.instrument_measurements USING btree (platform_id);


--
-- Name: fki_measurement_platform_id_fkey; Type: INDEX; Schema: public; Owner: vandaq
--

CREATE INDEX fki_measurement_platform_id_fkey ON public.measurement USING btree (platform_id);


--
-- Name: idx_acquisition_type_id; Type: INDEX; Schema: public; Owner: vandaq
--

CREATE INDEX idx_acquisition_type_id ON public.acquisition_type USING btree (id);


--
-- Name: idx_instrument_id; Type: INDEX; Schema: public; Owner: vandaq
--

CREATE INDEX idx_instrument_id ON public.instrument USING btree (id);


--
-- Name: idx_parameter_id; Type: INDEX; Schema: public; Owner: vandaq
--

CREATE INDEX idx_parameter_id ON public.parameter USING btree (id);


--
-- Name: idx_platform_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_platform_id ON public.platform USING btree (id) WITH (deduplicate_items='true');


--
-- Name: idx_sample_time_id; Type: INDEX; Schema: public; Owner: vandaq
--

CREATE INDEX idx_sample_time_id ON public.measurement USING btree (sample_time_id) WITH (deduplicate_items='true');


--
-- Name: idx_time_id; Type: INDEX; Schema: public; Owner: vandaq
--

CREATE INDEX idx_time_id ON public."time" USING btree (id);


--
-- Name: idx_unit_id; Type: INDEX; Schema: public; Owner: vandaq
--

CREATE INDEX idx_unit_id ON public.unit USING btree (id);


--
-- Name: instrument_measurements instrument_measurements_acquisition_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_acquisition_type_id_fkey FOREIGN KEY (acquisition_type_id) REFERENCES public.acquisition_type(id);


--
-- Name: instrument_measurements instrument_measurements_instrument_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_instrument_id_fkey FOREIGN KEY (instrument_id) REFERENCES public.instrument(id);


--
-- Name: instrument_measurements instrument_measurements_parameter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_parameter_id_fkey FOREIGN KEY (parameter_id) REFERENCES public.parameter(id);


--
-- Name: instrument_measurements instrument_measurements_platform_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_platform_id_fkey FOREIGN KEY (platform_id) REFERENCES public.platform(id);


--
-- Name: instrument_measurements instrument_measurements_unit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.instrument_measurements
    ADD CONSTRAINT instrument_measurements_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES public.unit(id);


--
-- Name: measurement measurement_acquisition_time_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_acquisition_time_id_fkey FOREIGN KEY (acquisition_time_id) REFERENCES public."time"(id);


--
-- Name: measurement measurement_acquisition_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_acquisition_type_id_fkey FOREIGN KEY (acquisition_type_id) REFERENCES public.acquisition_type(id);


--
-- Name: measurement measurement_instrument_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_instrument_id_fkey FOREIGN KEY (instrument_id) REFERENCES public.instrument(id);


--
-- Name: measurement measurement_instrument_time_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_instrument_time_id_fkey FOREIGN KEY (instrument_time_id) REFERENCES public."time"(id);


--
-- Name: measurement measurement_parameter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_parameter_id_fkey FOREIGN KEY (parameter_id) REFERENCES public.parameter(id);


--
-- Name: measurement measurement_platform_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_platform_id_fkey FOREIGN KEY (platform_id) REFERENCES public.platform(id);


--
-- Name: measurement measurement_sample_time_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_sample_time_id_fkey FOREIGN KEY (sample_time_id) REFERENCES public."time"(id);


--
-- Name: measurement measurement_unit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: vandaq
--

ALTER TABLE ONLY public.measurement
    ADD CONSTRAINT measurement_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES public.unit(id);


--
-- PostgreSQL database dump complete
--

