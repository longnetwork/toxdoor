# -*- coding: utf-8 -*-

# pylint: disable=E1101,W0621

import os, logging, threading
from importlib import resources

from random import shuffle
from itertools import zip_longest

from time import time, sleep


from ctypes import (
    POINTER, 
    py_object,
    
    pointer, string_at, c_char_p,
    c_ubyte, c_uint16,

    _CFuncPtr,
)

from .toxcore import tox, to_ct, to_py


BOOTSTRAP_NODES = [  # https://nodes.tox.chat/
                     # (IPv4:Port, Public Key),
]


BOOTSTRAP_FILE = 'bootstrap.txt'; BOOTSTRAP_FIELDS = 5


if not os.path.exists(BOOTSTRAP_FILE):  # Или в текущей директории (после python -m toxdoor bootstrap) или в пакете
    BOOTSTRAP_FILE = os.path.join(str(resources.files(__package__)), BOOTSTRAP_FILE)

if os.path.exists(BOOTSTRAP_FILE):
    with open(BOOTSTRAP_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = (line or '').strip()
            if line and not line.startswith('#'):
                parts = line.split('\t')
                if len(parts) < BOOTSTRAP_FIELDS: parts = parts + [''] * (BOOTSTRAP_FIELDS - len(parts))

                (ipv4,
                 ipv6,
                 port,
                 pubkey,
                 maintainer) = parts[0: BOOTSTRAP_FIELDS]                

                if ipv4 and port and pubkey:
                    if not ipv4.startswith('NONE'):
                        bootstrap = (ipv4 + ":" + port, pubkey)
                        if bootstrap not in BOOTSTRAP_NODES:
                            BOOTSTRAP_NODES.append(bootstrap)        


class MetaTox(type):
    """
        Чтобы __getattr__() работа при вызове на самом классе (Tox.name) для доступа
        к константам или нативным функциям с параметрами ctypes без авто преобразования
    """
    def __getattr__(cls, name):
        return getattr(tox, name)

class Tox(metaclass=MetaTox):
    """
        Класс подключения с автоматическими сервисами поллинга и обработки коллбэков в наследниках
    """

    BOOTSTRAP_TIMEOUT = 12.0;  # бутстрапинг длится до 10s (https://github.com/irungentoo/Tox_Client_Guidelines/blob/master/Required/Bootstrapping.md)

    
    def __init__(self, iter_priority: "sleep time, s" = 0.005, **opts):
        """
            struct Tox_Options {
                bool ipv6_enabled;
                bool udp_enabled;
                bool local_discovery_enabled;
                bool dht_announcements_enabled;
                Tox_Proxy_Type proxy_type;
                const char *proxy_host;
                uint16_t proxy_port;
                uint16_t start_port;
                uint16_t end_port;
                uint16_t tcp_port;
                bool hole_punching_enabled;
                Tox_Savedata_Type savedata_type;  // 0 - NONE; 1 - TOX_SAVE; 2 - SECRET_KEY
                const uint8_t *savedata_data;
                size_t savedata_length;
                tox_log_cb *log_callback;
                void *log_user_data;
                bool experimental_thread_safety;
                bool experimental_groups_persistence;
            };

            RuntimeErrors: TOX_ERR_NEW_OK, TOX_ERR_NEW_NULL, TOX_ERR_NEW_MALLOC, TOX_ERR_NEW_PORT_ALLOC, TOX_ERR_NEW_PROXY_BAD_TYPE,
               TOX_ERR_NEW_PROXY_BAD_HOST, TOX_ERR_NEW_PROXY_BAD_PORT, TOX_ERR_NEW_PROXY_NOT_FOUND, TOX_ERR_NEW_LOAD_ENCRYPTED,
               TOX_ERR_NEW_LOAD_BAD_FORMAT,


            iter_priority чтобы не загружать процессор. Должно быть существенно меньше 0.05s
            
        """

    
        self._toxptr: "struct Tox *" = None


        # По умолчанию Режим восстановления состояния Tox с тем-же toxID (TOX_SAVE)
        # Для восстановления toxID по SECRET_KEY обязательно задать savedata_type = 2


        savedata_data = opts.get('savedata_data')

        if isinstance(savedata_data, str):
            savedata_data = bytes.fromhex(savedata_data)
        
        if savedata_data:
            opts['savedata_length'] = len(savedata_data)
        
        if 'savedata_type' not in opts:
            if opts.get('savedata_length'):
                opts['savedata_type'] = 1
        else:
            if not opts.get('savedata_length'):
                opts['savedata_type'] = 0

        
        self.opts: "struct Tox_Options" = Tox.Options(); Tox.options_default(pointer(self.opts));  # Подготовка полей опций


        if opts:                                                                                 # Накатили опции из конструктора
            for k, v in opts.items():                                                            # (Будут передаваться в вызовах pointer)
                fld = getattr(self.opts, k, None)
                if fld is not None:
                    v = to_ct(v, type(fld))
                    setattr(self.opts, k, v)

        
        setattr(self, '__log_cb', cb := Tox.log_cb(  # XXX Обязаны удерживать ссыль на колбэк из-за GC
            # Это единственный колбэк (служебный) который устанавливается через опции. Остальные штатно через вызов Tox.callback_...
            # typedef void tox_log_cb(Tox *tox, Tox_Log_Level level, const char *file, uint32_t line, const char *func, const char *message, void *user_data);
            # tox_log_cb = ctypes.CFUNCTYPE(
            #     None,
            #     POINTER_T(struct_Tox), Tox_Log_Level, POINTER_T(ctypes.c_char), ctypes.c_uint32, POINTER_T(ctypes.c_char), POINTER_T(ctypes.c_char), POINTER_T(None)
            # )
            
            lambda _tp, level, _file, _line, _func, message, _user_data: (
            
                logging_level := logging.getLogger().level // 10,
                
                msg := f"{repr(self)}: {string_at(message).decode(errors='backslashreplace')}",
                
                None if level < logging_level else
                # print(msg) if level >= 4 else
                # print(msg) if level >= 3 else
                # print(msg) if level >= 2 else
                # print(msg) if level >= 1 else
                logging.error(msg) if level >= 4 else
                logging.warning(msg) if level >= 3 else
                logging.info(msg) if level >= 2 else
                logging.debug(msg) if level >= 1 else
                None,
            )[-1]
        ))
        Tox.options_set_log_callback(pointer(self.opts), cb)

        repr_opts = f"{[ f + '=' + str(getattr(self.opts, f)) for f, _ in self.opts._fields_ ]}"
        logging.debug(f"Tox Options: {repr_opts}")


        # XXX C language treats enumeration constants as type int
        #     c_void_p ~ POINTER(None)

        # Tox *tox_new(const Tox_Options *options, Tox_Err_New *error);
        self._toxptr = Tox.new(pointer(self.opts), pointer(error := Tox.Err_New()))
        if error.value != Tox.ERR_NEW_OK:
            raise RuntimeError(f"{type(self).__name__}: {string_at(Tox.err_new_to_string(error)).decode(errors='backslashreplace')}")


        # Инициализируем колбэки если они определены в наследниках
        # Либо должны оканчиваться на `_cb` как в toxcore либо начинаться на `on_` но не одновременно
        # Остальная часть имени также как в toxcore (можно без префикса tox_)
        
        # for name, method in type(self).__dict__.items():  # XXX на инстанце наследника type(self).__dict__ дает методы только в наследнике
        for name in dir(type(self)):
            if name.startswith('__'): continue
            method = getattr(self, name)
            if callable(method):
                if name.startswith('tox_'):
                    name = name[4:]
                    
                if name.endswith('_cb'):
                    
                    tox_cb_t = getattr(tox, name);  # ctypes.CFUNCTYPE(...)
                    tox_set_cb = getattr(tox, 'callback_' + name[:-3])
                    
                elif name.startswith('on_'):

                    tox_cb_t = getattr(tox, name[3:] + '_cb');  # ctypes.CFUNCTYPE(...)
                    tox_set_cb = getattr(tox, 'callback_' + name[3:])
                    
                else:
                    continue

                # Назначаем колбэки, помня про замыкания (мы в цикле)
                # Удерживаем ссыль на колбек в self.__<name>, внутри колбека вызывается python-метод инстанца self

                # name схвачено в замыкании. getattr(self, ...) не явно биндит метот к self
                # typedef void tox_<name>_cb(Tox *tox, ...);

                restype = getattr(tox_cb_t, '_restype_', None); argtypes = getattr(tox_cb_t, '_argtypes_', tuple())

                def _cb_call(_tp, *args, name=name, restype=restype, argtypes=argtypes):  # Замыкание по name, restype, argtypes

                    # Колбеки всегда имеют первый параметр указывающий на _toxptr (_tp)
                    py_args = [ to_py(ctobj, ct) for ctobj, ct in zip_longest(args, argtypes[1:]) ]

                    ret = getattr(self, name)(*py_args)
                    
                    return to_ct(ret, restype)
                
                cb = tox_cb_t( _cb_call )

                # XXX коллбек устанавливаемый здесь может быть только один
                setattr(self, '__' + name, cb);  tox_set_cb(self._toxptr, cb);  # Удерживаем ссыль на колбек и назначаем его

        self._getattr_cache = {};  # Кеш оберток self.__getattr__()


        self.tlock = threading.RLock()

        self._iter_time = None
        self._iter_thread = None
        self._iter_priority = iter_priority
        
        self.start_iterate()
        

    def start_iterate(self):
        if self._iter_thread is None:
            self._iter_thread = threading.Thread(target=self._iter_run, daemon=True)
            self._iter_thread.start()
        
    def stop_iterate(self):
        if self._iter_thread is not None:
            self._iter_thread = None;  # Атомарная


    def __del__(self):
        if self._toxptr:
            try:
                with self.tlock:
                    Tox.kill(self._toxptr); self._toxptr = None
            except Exception as e:
                logging.error(f"tox_kill: {e}")

    

    def __getattr__(self, name):

        _getattr_cache = self._getattr_cache; _toxptr = self._toxptr
        
        
        if name in _getattr_cache:
            return _getattr_cache[name]
        

        tox_attr = getattr(tox, name)
        if isinstance(tox_attr, _CFuncPtr):
            restype = getattr(tox_attr, 'restype', None); argtypes = getattr(tox_attr, 'argtypes', [])

            static_call = True
            if argtypes and argtypes[0] is POINTER(Tox.struct_Tox):
                argtypes = argtypes[1:]
                static_call = False
                
            def wrap(*args):
                
                ct_args = [ to_ct(pyobj, ct) for pyobj, ct in zip_longest(args, argtypes) ];  # Скип POINTER_T(struct_Tox) (это как бы си-шный self)

                if static_call:
                    ret = tox_attr(*ct_args)
                else:
                    ret = tox_attr(_toxptr, *ct_args)

                return to_py(ret, restype)

            wrap.tox_attr = tox_attr
            wrap.__name__ = name

            _getattr_cache[name] = wrap
            return wrap
            
        else:
            _getattr_cache[name] = tox_attr
            return tox_attr



    def _iterate(self, user_data=None):
        """
            toxcore требует что-бы вызовы iterate() были не чаще чем значение iteration_interval(), ms

            XXX Блокирующая. Вызывать только в потоке

            user_data это любые пользовательские данные возвращаемые в колбэках
        """
        
        user_data_p = pointer(py_object(user_data)) if user_data is not None else None;  # None ~ c_void_p()
        
        with self.tlock:
            if self._iter_time is None:
                Tox.iterate(self._toxptr, user_data_p)
                self._iter_time = time();      # Момент последней итерации
                return

            iteration_interval = Tox.iteration_interval(self._toxptr) / 1000.0;  # s
                
            dtime = time() - self._iter_time;  # Время с последней итерации 

            if dtime < iteration_interval:
                sleep(iteration_interval - dtime)
                
                Tox.iterate(self._toxptr, user_data_p)
                self._iter_time += iteration_interval
                return

            # Немедленная итерация (долго не было)
            
            Tox.iterate(self._toxptr, user_data_p)
            self._iter_time += dtime
            return

    def _iter_run(self):
        """
            При использовании интерфейса мы не заморачиваемся системным поллингом ядра (он происходит автоматом в потоке _iter_run)
        """
        _iter_thread_id = id(self._iter_thread)
        
        while self._iter_thread and _iter_thread_id == id(self._iter_thread):  # Маркер завершения после вызова self.stop_iterate()
                                                                               # Даже если быстро дать новый self.start_iterate(),
                                                                               # то старый висячий поток не останется
            self._iterate()

            if self._iter_priority is not None:
                sleep(self._iter_priority)

    
    def connect(self, bootstraps=None):
        """
            Согласно Tox Client Guidelines (https://github.com/irungentoo/Tox_Client_Guidelines/blob/master/Required/Bootstrapping.md),
            клиент каждые 5 секунд должен пытаться подключиться как минимум к четырем случайным нодам,
            пока ядро не сообщит об успешном соединении (см. tox_self_connection_status_cb).
            В случае загрузки из файла состояния клиент не должен пытаться соединяться в течении 10 секунд после первого вызова tox_iterate и,
            в случае отсутствия соединения, повторить агрессивную стратегию соединения выше.

            XXX Короче во вне проверять раз в 10 секунд self_get_connection_status() и если нет подключения снова вызвать connect()
                Помним про self.tlock (у нас для Tox.iterate() отдельный поток)
        """
        with self.tlock:

            if bootstraps is None:
                bootstraps = BOOTSTRAP_NODES
            
            if bootstraps:
                bootstraps = bootstraps.copy(); shuffle(bootstraps);  # (ipv4 + ":" + port, pubkey)

                for url, pubkey in bootstraps:
                    addr, *port = url.split(':'); port = int(port and port[0] or 33445); pubkey = bytes.fromhex(pubkey)

                    assert len(pubkey) == Tox.public_key_size()

                    # bool tox_bootstrap(Tox *tox, const char *host, uint16_t port, const uint8_t public_key[TOX_PUBLIC_KEY_SIZE], Tox_Err_Bootstrap *error);

                    # Tox.bootstrap(self._toxptr, c_char_p(addr.encode()), c_uint16(port), (c_ubyte * len(pubkey))(*pubkey), POINTER(Tox.Err_Bootstrap)(error := Tox.Err_Bootstrap()))
                    Tox.bootstrap(self._toxptr, c_char_p(addr.encode()), c_uint16(port), (c_ubyte * len(pubkey))(*pubkey), pointer(error := Tox.Err_Bootstrap()))
                    if error.value != Tox.ERR_BOOTSTRAP_OK:
                        logging.warning(f"{type(self).__name__}: {string_at(Tox.err_bootstrap_to_string(error)).decode(errors='backslashreplace')} ({addr}:{port})")
                        
        
    def join(self, timeout=None):
        """
            Вся работа может быть только по коллбекам и нам нужен механизм спячки
        """
        t = None
        with self.tlock:
            if not ((t := self._iter_thread) and t.is_alive()):
                t = None

        if t:
            t.join(timeout)
    

    @staticmethod
    def calculate_address(_public_key, _nospam):
        
        public_key_size, nospam_size = Tox.public_key_size(), Tox.nospam_size()
        
        if isinstance(_public_key, str):
            public_key = bytes.fromhex(_public_key)[0: public_key_size]
        elif isinstance(_public_key, (bytes, bytearray)):
            public_key = _public_key[0: public_key_size]
        elif isinstance(_public_key, memoryview):
            public_key = _public_key[0: public_key_size].tobytes()
        else:
            raise TypeError(f"Unsupported public_key type: {type(_public_key)}")

        
        if isinstance(_nospam, str):
            nospam = bytes.fromhex(_nospam)[0: nospam_size]
        elif isinstance(_nospam, (bytes, bytearray)):
            nospam = _nospam[0: nospam_size]
        elif isinstance(_nospam, memoryview):
            nospam = _nospam[0: nospam_size].tobytes()
        elif isinstance(_nospam, int):
            nospam = _nospam.to_bytes(nospam_size, 'big')
        else:
            raise TypeError(f"Unsupported nospam type: {type(_nospam)}")


        address, crc = public_key + nospam, bytearray(2)

        for i, b in enumerate(address): crc[i % 2] = crc[i % 2] ^ b

        return address + crc













        
    
